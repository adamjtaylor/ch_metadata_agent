from google.cloud import bigquery
import synapseclient
import os
from tqdm import tqdm

# Run BigQuery query
client = bigquery.Client()
query = """
SELECT 
  DISTINCT CONCAT(channel_metadata_synapseId, ".", channel_metadata_version) as channel_synid, 
  img.Imaging_Assay_Type as imaging_assay_type,
  img.HTAN_Center as htan_center
FROM `htan-dcc.released.entities_v7_0` r7
LEFT JOIN `htan-dcc.combined_assays.ImagingLevel2` img
  ON r7.entityId = img.entityId
WHERE channel_metadata_synapseId IS NOT NULL
  AND NOT Imaging_Assay_Type = "MERFISH" 
"""
results = client.query(query).result()

results_df = results.to_dataframe()


print(f"Retrieved {results.total_rows} records from BigQuery.")

print(results_df.head())

# Save results to json
results_df.to_json("htan_channel_metadata_records.json", orient="records", lines=True)

# Fetch from Synapse
syn = synapseclient.login()
for _, row in tqdm(results_df.iterrows(), total=results_df.shape[0]):
    entity = syn.get(row.channel_synid, downloadLocation="htan_data/", silent=True)
    ext = os.path.splitext(entity.path)[1]
    new_path = os.path.join("htan_data", f"{entity.id}{ext}")
    os.rename(entity.path, new_path)
    print(f"Fetched: {entity.id}")
