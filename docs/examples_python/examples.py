# %%
import time

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

currtime = time.time()
l2_edit = get_operation_level2_edit(edit_id, client)
print(f"{time.time() - currtime:.3f} seconds elapsed.")

# %%
from paleo import get_operations_level2_edits

currtime = time.time()
l2_edits = get_operations_level2_edits(change_log.index, client)
print(f"{time.time() - currtime:.3f} seconds elapsed.")

# %%
from paleo import get_root_level2_edits

currtime = time.time()
l2_edits = get_root_level2_edits(root_id, client)
print(f"{time.time() - currtime:.3f} seconds elapsed.")

# %%
l2_edits

# %%
l2_edits[9028]

# %%
l2_edits[25672]

# %%
l2_edits[9028] + l2_edits[25672]

# %%

from paleo import get_metaedits

metaedits, metaedit_mapping = get_metaedits(l2_edits)

# %%
member_edits = metaedit_mapping[23]

# %%
metaedits[23].added_nodes

# %%
for edit in member_edits:
    print(list(l2_edits[edit].added_nodes.index))

# %%
