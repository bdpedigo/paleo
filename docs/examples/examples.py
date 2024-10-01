# %%
from caveclient import CAVEclient
from paleo import get_detailed_change_log

root_id = 864691135639556411

client = CAVEclient("minnie65_phase3_v1")

change_log = get_detailed_change_log(root_id, client, filtered=False)

# %%
from paleo import get_level2_edits

edits = get_level2_edits(
    root_id,
    client,
    verbose=True,
    bounds_halfwidth=20_000,
)

# %%
edits[9028]

# %%
