"""
Base Agent class for the antibody curation system.
Implements the core feedback loop: gather context → take action → verify work.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path


class AgentStatus(Enum):
    """Status of agent execution."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Result from agent execution."""
    status: AgentStatus
    data: Any
    errors: List[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict:
        return {
            'status': self.status.value,
            'data': self.data,
            'errors': self.errors,
            'metadata': self.metadata
        }


class BaseAgent(ABC):
    """
    Base class for all agents in the system.
    Implements the core agent pattern from Claude Agent SDK.
    """

    def __init__(self, name: str, config: Optional[Dict] = None):
        """
        Initialize agent.

        Args:
            name: Agent name
            config: Configuration dictionary
        """
        self.name = name
        self.config = config or {}
        self.status = AgentStatus.IDLE
        self.context = {}

    @abstractmethod
    def gather_context(self, input_data: Any) -> Dict:
        """
        Gather context phase: collect information needed for action.

        Args:
            input_data: Input data for the agent

        Returns:
            Context dictionary
        """
        pass

    @abstractmethod
    def take_action(self, context: Dict) -> Any:
        """
        Take action phase: perform the main work.

        Args:
            context: Context gathered in previous phase

        Returns:
            Result of the action
        """
        pass

    @abstractmethod
    def verify_work(self, result: Any, context: Dict) -> tuple[bool, List[str]]:
        """
        Verify work phase: check if the work was done correctly.

        Args:
            result: Result from take_action
            context: Original context

        Returns:
            Tuple of (success: bool, errors: List[str])
        """
        pass

    def execute(self, input_data: Any, max_iterations: int = 3) -> AgentResult:
        """
        Execute the agent with feedback loop.

        Args:
            input_data: Input data
            max_iterations: Maximum retry iterations

        Returns:
            AgentResult
        """
        self.status = AgentStatus.RUNNING
        errors = []

        for iteration in range(max_iterations):
            try:
                # Phase 1: Gather context
                context = self.gather_context(input_data)
                self.context = context

                # Phase 2: Take action
                result = self.take_action(context)

                # Phase 3: Verify work
                success, verification_errors = self.verify_work(result, context)

                if success:
                    self.status = AgentStatus.COMPLETED
                    return AgentResult(
                        status=AgentStatus.COMPLETED,
                        data=result,
                        errors=[],
                        metadata={'iterations': iteration + 1}
                    )
                else:
                    errors.extend(verification_errors)

                    # If not last iteration, retry
                    if iteration < max_iterations - 1:
                        print(f"{self.name}: Verification failed, retrying... (iteration {iteration + 1})")
                        continue

            except Exception as e:
                errors.append(f"Exception in iteration {iteration + 1}: {str(e)}")
                if iteration < max_iterations - 1:
                    continue

        # If we get here, all iterations failed
        self.status = AgentStatus.FAILED
        return AgentResult(
            status=AgentStatus.FAILED,
            data=None,
            errors=errors,
            metadata={'iterations': max_iterations}
        )

    def save_state(self, state_dir: Path):
        """Save agent state to disk."""
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / f"{self.name}_state.json"

        state = {
            'name': self.name,
            'status': self.status.value,
            'context': self.context,
            'config': self.config
        }

        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def load_state(self, state_dir: Path):
        """Load agent state from disk."""
        state_file = state_dir / f"{self.name}_state.json"

        if not state_file.exists():
            return

        with open(state_file) as f:
            state = json.load(f)

        self.status = AgentStatus(state['status'])
        self.context = state['context']
        self.config = state.get('config', {})
