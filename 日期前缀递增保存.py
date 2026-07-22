import maya.cmds as cmds
import os
import re
from datetime import datetime

EXT = "mb"


def prefix_increment_save():
    current_path = cmds.file(q=True, sceneName=True)
    if not current_path:
        cmds.SaveSceneAs()
        return

    folder = os.path.dirname(current_path)
    base_name = os.path.splitext(os.path.basename(current_path))[0]

    now = datetime.now()
    date_prefix = now.strftime("%Y%m%d_%H%M")

    existing_pattern = re.compile(
        r"^(\d{8}_\d{4})_(\d{4})_(.+)\.(ma|mb)$",
        re.IGNORECASE
    )

    m = existing_pattern.match(os.path.basename(current_path))
    if m:
        core_name = m.group(3)
        current_num = int(m.group(2))
        start_num = current_num + 1
    else:
        core_name = base_name
        start_num = 1

    scan_pattern = re.compile(
        r"^\d{8}_\d{4}_(\d{4})_" + re.escape(core_name) + r"\.(ma|mb)$",
        re.IGNORECASE
    )

    max_num = start_num - 1
    for f in os.listdir(folder):
        sm = scan_pattern.match(f)
        if sm:
            n = int(sm.group(1))
            if n > max_num:
                max_num = n

    new_num = max_num + 1
    new_filename = "%s_%04d_%s.%s" % (date_prefix, new_num, core_name, EXT)
    new_full_path = os.path.join(folder, new_filename)

    cmds.file(rename=new_full_path)
    cmds.file(save=True, type="mayaAscii" if EXT == "ma" else "mayaBinary")

    print("Saved: %s" % new_full_path)


prefix_increment_save()
