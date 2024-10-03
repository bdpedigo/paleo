# %%
from caveclient import CAVEclient
from paleo import get_detailed_change_log

root_id = 864691135639556411

client = CAVEclient("minnie65_phase3_v1")

change_log = get_detailed_change_log(root_id, client, filtered=False)

# %%
edit_id = change_log.index[0]

edit_id

# %%
from paleo import get_operation_level2_edit

l2_edit = get_operation_level2_edit(edit_id, client)

# %%
from paleo import get_operations_level2_edits

l2_edits = get_operations_level2_edits(change_log.index[:50], client)

# %%
from datetime import datetime, timedelta

import numpy as np

seg_resolution = client.chunkedgraph.base_resolution

details = client.chunkedgraph.get_operation_details([edit_id])[str(edit_id)]
roots = details["roots"]
ts = datetime.fromisoformat(details["timestamp"])
delta = timedelta(microseconds=1)
pre_ts = ts - delta
post_ts = ts + delta

maps = client.chunkedgraph.get_past_ids(roots, timestamp_past=pre_ts)
old_roots = []
for root in roots:
    old_roots.extend(maps["past_id_map"][root])

point_in_cg = np.array(details["sink_coords"][0])

point_in_nm = point_in_cg * seg_resolution

# %%
import time

from paleo import get_operations_level2_edits

currtime = time.time()

get_operations_level2_edits(change_log.index.to_list(), client)
print(f"{time.time() - currtime:.3f} seconds elapsed.")


# %%
from paleo import get_level2_edits

edits = get_level2_edits(
    root_id,
    client,
    verbose=True,
    bounds_halfwidth=20_000,
)

# %%
edits

# %%
edits[9028]

# %%
edits[25672]

# %%
edits[9028] + edits[25672]

# %%

from paleo import get_metaedits

metaedits, metaedit_mapping = get_metaedits(edits)

# %%
member_edits = metaedit_mapping[23]

# %%
metaedits[23].added_nodes

# %%
for edit in member_edits:
    print(list(edits[edit].added_nodes.index))

# %%
