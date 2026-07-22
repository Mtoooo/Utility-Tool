# -*- coding: utf-8 -*-
import maya.cmds as cmds
import time

WINDOW_NAME = "m341_reNamer_py_v22"
DEBUG = True
_debug_records = []
COLLAPSED_HEIGHT = 210

# ============================================================
# 在这里设置预设名称和备注
# ------------------------------------------------------------
# 格式：[ ["预设名", "备注文字"]
# 备注只是提示用的，显示在预设按钮后面，用方括号括起来
# 备注不影响重命名功能，按钮功能和以前一样
# 增加一行就多一个预设，删掉一行就少一个预设
#
# 示例：
#   ["Low", "低模"]     → 按钮显示 Low  后面显示 [低模]
#   ["High", "高模"]    → 按钮显示 High 后面显示 [高模]
#   ["Cage", "烘焙笼子"]  → 按钮显示 Cage 后面显示 [烘焙笼子]
#   ["A", "枪身"]       → 按钮显示 A    后面显示 [枪身]
# ============================================================
PRESET_NAMES = [
    ["grp_body", "主体机匣"],
    ["grp_barrel", "枪管总成"],
    ["grp_handguard", "护木"],
    ["grp_stock", "枪托总成"],
    ["grp_magazine", "弹匣"],
    ["grp_trigger", "扳机组件"],
    ["grp_sight_optics", "光学瞄具"],
    ["grp_sight_iron", "机械瞄具"],
    ["grp_accessories", "战术附件"],
    ["grp_muzzle_device", "枪口装置"],
    ["grp_bolt", "枪机"],
    ["grp_firing_group", "发射机组"],
    ["grp_decal", "贴纸"],
    ["grp_Slide", "滑套"],
    ["grp_magazine", "子弹"],
]
# ============================================================

def debug_log(func, old_name, new_name, status="OK"):
    t = time.strftime("%H:%M:%S")
    if status == "SKIP":
        msg = "[%s] [%s] %s -- 跳过 (%s)" % (t, func, old_name, new_name)
    elif status == "FAIL":
        msg = "[%s] [%s] %s -> %s -- 失败" % (t, func, old_name, new_name)
    else:
        msg = "[%s] [%s] %s -> %s" % (t, func, old_name, new_name)
    _debug_records.append(msg)
    if len(_debug_records) > 200:
        _debug_records.pop(0)
    if DEBUG:
        print(msg)

def debug_log_summary(func, text):
    t = time.strftime("%H:%M:%S")
    msg = "[%s] [%s] === %s ===" % (t, func, text)
    _debug_records.append(msg)
    if len(_debug_records) > 200:
        _debug_records.pop(0)
    if DEBUG:
        print(msg)

def get_selected():
    sel = cmds.ls(selection=True, long=True, transforms=True)
    if not sel:
        cmds.confirmDialog(title="提示", message="请先选中要操作的模型/对象！", button=["确定"])
        return []
    debug_log("选中", "%d objects" % len(sel), "", "OK")
    return sel

def get_short_name(obj):
    return obj.split("|")[-1]

def update_status(text):
    if cmds.text("status_txt", exists=True):
        cmds.text("status_txt", edit=True, label=text)

def get_alpha_suffix(index):
    letters = []
    n = index
    while True:
        n, r = divmod(n, 26)
        letters.append(chr(65 + r))
        if n == 0:
            break
        n -= 1
    return ''.join(reversed(letters))

def do_rename(*args):
    name = cmds.textField("tf_name", query=True, text=True)
    if not name:
        update_status("请先在命名框中输入内容")
        return
    sel = get_selected()
    if not sel:
        return
    inc_idx = cmds.optionMenu("opt_increment", query=True, select=True)
    inc_names = {1: "_A", 2: "1", 3: "_1", 4: "_01", 5: "_001", 6: "_0001", 7: "_LOD_0"}
    debug_log("rename", "输入=%s 递增=%s" % (name, inc_names.get(inc_idx, "?")), "%d objects" % len(sel), "OK")
    success = 0
    for i, obj in enumerate(sel):
        old = get_short_name(obj)
        try:
            if inc_idx == 1:
                new_name = name + "_" + get_alpha_suffix(i)
            elif inc_idx == 2:
                new_name = name + str(i + 1)
            elif inc_idx == 3:
                new_name = name + "_" + str(i + 1)
            elif inc_idx == 4:
                new_name = name + "_" + str(i + 1).zfill(2)
            elif inc_idx == 5:
                new_name = name + "_" + str(i + 1).zfill(3)
            elif inc_idx == 6:
                new_name = name + "_" + str(i + 1).zfill(4)
            elif inc_idx == 7:
                new_name = name + "_LOD_" + str(i)
            else:
                new_name = name + "_" + str(i + 1)
            cmds.rename(obj, new_name)
            debug_log("rename", old, new_name, "OK")
            success += 1
        except:
            debug_log("rename", old, "(error)", "FAIL")
    debug_log_summary("rename", "Done: %d/%d" % (success, len(sel)))
    update_status("已重命名 %d 个" % success)

def do_replace(*args):
    find_str = cmds.textField("tf_name", query=True, text=True)
    rep_str = cmds.textField("tf_replace", query=True, text=True)
    if not find_str:
        update_status("请先在命名框中输入要查找的文字")
        return
    sel = get_selected()
    if not sel:
        return
    debug_log("replace", "find=%s replace=%s" % (find_str, rep_str), "%d objects" % len(sel), "OK")
    success = 0
    for obj in sel:
        old_name = get_short_name(obj)
        if find_str in old_name:
            try:
                new_name = old_name.replace(find_str, rep_str)
                cmds.rename(obj, new_name)
                debug_log("replace", old_name, new_name, "OK")
                success += 1
            except:
                debug_log("replace", old_name, "(error)", "FAIL")
    debug_log_summary("replace", "Done: %d/%d" % (success, len(sel)))
    update_status("已将 %s 替换为 %s，成功 %d 个" % (find_str, rep_str, success))

def do_prefix(*args):
    text = cmds.textField("tf_name", query=True, text=True)
    if not text:
        update_status("请先在命名框中输入内容")
        return
    sel = get_selected()
    if not sel:
        return
    debug_log("前缀", "prefix=%s" % text, "%d objects" % len(sel), "OK")
    success = 0
    for obj in sel:
        old = get_short_name(obj)
        try:
            cmds.rename(obj, text + old)
            debug_log("前缀", old, text + old, "OK")
            success += 1
        except:
            debug_log("前缀", old, "(error)", "FAIL")
    debug_log_summary("前缀", "Done: %d/%d" % (success, len(sel)))
    update_status("已添加前缀 %s，成功 %d 个" % (text, success))

def do_suffix(*args):
    text = cmds.textField("tf_name", query=True, text=True)
    if not text:
        update_status("请先在命名框中输入内容")
        return
    sel = get_selected()
    if not sel:
        return
    debug_log("后缀", "suffix=%s" % text, "%d objects" % len(sel), "OK")
    success = 0
    for obj in sel:
        old = get_short_name(obj)
        try:
            cmds.rename(obj, old + text)
            debug_log("后缀", old, old + text, "OK")
            success += 1
        except:
            debug_log("后缀", old, "(error)", "FAIL")
    debug_log_summary("后缀", "Done: %d/%d" % (success, len(sel)))
    update_status("已添加后缀 %s，成功 %d 个" % (text, success))

def add_suffix_preset(suffix_text, *args):
    sel = get_selected()
    if not sel:
        return
    debug_log("后缀_%s" % suffix_text, "add suffix", "%d objects" % len(sel), "OK")
    success = 0
    for obj in sel:
        old = get_short_name(obj)
        try:
            cmds.rename(obj, old + suffix_text)
            debug_log("后缀_%s" % suffix_text, old, old + suffix_text, "OK")
            success += 1
        except:
            debug_log("后缀_%s" % suffix_text, old, "(error)", "FAIL")
    debug_log_summary("后缀_%s" % suffix_text, "Done: %d/%d" % (success, len(sel)))
    update_status("已添加后缀 %s，成功 %d 个" % (suffix_text, success))

def _batch_delete_char(obj_list, func_label, char_fn):
    short_names = []
    for obj in obj_list:
        old = get_short_name(obj)
        if len(old) <= 1:
            continue
        short_names.append(old)
    if not short_names:
        return 0, 0
    short_names.reverse()
    success = 0
    fail = 0
    used_names = set()
    freeing_names = set(short_names)
    for old_name in short_names:
        target_base = char_fn(old_name)
        final_name = target_base
        counter = 1
        while (final_name in used_names or
               (final_name not in freeing_names and cmds.objExists(final_name))):
            final_name = target_base + str(counter)
            counter += 1
        try:
            cmds.rename(old_name, final_name)
            used_names.add(final_name)
            debug_log(func_label, old_name, final_name, "OK")
            success += 1
        except Exception as e:
            debug_log(func_label, old_name, str(e), "FAIL")
            fail += 1
    return success, fail

def del_first_char(*args):
    sel = get_selected()
    if not sel:
        return
    debug_log("删除首字", "action", "%d objects" % len(sel), "OK")
    success, fail = _batch_delete_char(sel, "删除首字", lambda n: n[1:])
    debug_log_summary("删除首字", "Done: ok=%d fail=%d" % (success, fail))
    msg = "已删除首字符，成功 %d 个" % success
    if fail > 0:
        msg += "，失败 %d 个" % fail
    update_status(msg)

def del_last_char(*args):
    sel = get_selected()
    if not sel:
        return
    debug_log("删除尾字", "action", "%d objects" % len(sel), "OK")
    success, fail = _batch_delete_char(sel, "删除尾字", lambda n: n[:-1])
    debug_log_summary("删除尾字", "Done: ok=%d fail=%d" % (success, fail))
    msg = "已删除尾字符，成功 %d 个" % success
    if fail > 0:
        msg += "，失败 %d 个" % fail
    update_status(msg)

def toggle_debug(*args):
    global DEBUG
    DEBUG = not DEBUG
    print("调试模式: %s" % ("ON" if DEBUG else "OFF"))

# ---- 预设前缀 ----
def do_preset_prefix(preset_name, *args):
    sel = get_selected()
    if not sel:
        return
    debug_log("预设前缀_%s" % preset_name, "add prefix", "%d objects" % len(sel), "OK")
    success = 0
    for obj in sel:
        old = get_short_name(obj)
        try:
            cmds.rename(obj, preset_name + old)
            debug_log("预设前缀_%s" % preset_name, old, preset_name + old, "OK")
            success += 1
        except:
            debug_log("预设前缀_%s" % preset_name, old, "(error)", "FAIL")
    debug_log_summary("预设前缀_%s" % preset_name, "Done: %d/%d" % (success, len(sel)))
    update_status("已添加前缀 %s，成功 %d 个" % (preset_name, success))

# ---- 预设后缀 ----
def do_preset_suffix(preset_name, *args):
    sel = get_selected()
    if not sel:
        return
    debug_log("预设后缀_%s" % preset_name, "add suffix", "%d objects" % len(sel), "OK")
    success = 0
    for obj in sel:
        old = get_short_name(obj)
        try:
            cmds.rename(obj, old + preset_name)
            debug_log("预设后缀_%s" % preset_name, old, old + preset_name, "OK")
            success += 1
        except:
            debug_log("预设后缀_%s" % preset_name, old, "(error)", "FAIL")
    debug_log_summary("预设后缀_%s" % preset_name, "Done: %d/%d" % (success, len(sel)))
    update_status("已添加后缀 %s，成功 %d 个" % (preset_name, success))

# ---- 预设重命名 ----
def do_preset_rename(preset_name, *args):
    sel = get_selected()
    if not sel:
        return
    inc_idx = cmds.optionMenu("opt_increment", query=True, select=True)
    debug_log("预设重命名_%s" % preset_name, "rename", "%d objects" % len(sel), "OK")
    success = 0
    for i, obj in enumerate(sel):
        old = get_short_name(obj)
        try:
            if inc_idx == 1:
                new_name = preset_name + "_" + get_alpha_suffix(i)
            elif inc_idx == 2:
                new_name = preset_name + str(i + 1)
            elif inc_idx == 3:
                new_name = preset_name + "_" + str(i + 1)
            elif inc_idx == 4:
                new_name = preset_name + "_" + str(i + 1).zfill(2)
            elif inc_idx == 5:
                new_name = preset_name + "_" + str(i + 1).zfill(3)
            elif inc_idx == 6:
                new_name = preset_name + "_" + str(i + 1).zfill(4)
            elif inc_idx == 7:
                new_name = preset_name + "_LOD_" + str(i)
            else:
                new_name = preset_name + "_" + str(i + 1)
            cmds.rename(obj, new_name)
            debug_log("预设重命名_%s" % preset_name, old, new_name, "OK")
            success += 1
        except:
            debug_log("预设重命名_%s" % preset_name, old, "(error)", "FAIL")
    debug_log_summary("预设重命名_%s" % preset_name, "Done: %d/%d" % (success, len(sel)))
    update_status("已重命名为 %s，成功 %d 个" % (preset_name, success))

def toggle_presets(*args):
    checked = cmds.checkBox("cb_presets", query=True, value=True)
    if cmds.frameLayout("preset_frame", exists=True):
        cmds.frameLayout("preset_frame", edit=True, visible=checked)
    if cmds.window(WINDOW_NAME, exists=True):
        preset_count = len(PRESET_NAMES)
        expanded_height = COLLAPSED_HEIGHT + preset_count * 22 + 10
        if checked:
            cmds.window(WINDOW_NAME, edit=True, height=expanded_height)
        else:
            cmds.window(WINDOW_NAME, edit=True, height=COLLAPSED_HEIGHT)

def create_ui():
    try:
        if cmds.window(WINDOW_NAME, exists=True):
            cmds.deleteUI(WINDOW_NAME)
        if cmds.window(WINDOW_NAME, exists=True):
            cmds.deleteUI(WINDOW_NAME)
    except:
        pass

    cmds.window(
        WINDOW_NAME,
        title="批量重命名工具 v2.2",
        width=240,
        height=COLLAPSED_HEIGHT,
        sizeable=True,
        resizeToFitChildren=False
    )

    main = cmds.columnLayout(adjustableColumn=True, rowSpacing=2)

    cmds.textField("tf_name", width=220)

    cmds.rowLayout(numberOfColumns=3, columnWidth3=(38, 4, 178))
    cmds.button(label="replace", command=do_replace, height=18,
                backgroundColor=(0.51, 0.51, 0.51))
    cmds.text(label=" ")
    cmds.textField("tf_replace", width=178)
    cmds.setParent(main)

    cmds.rowLayout(numberOfColumns=5, columnWidth5=(20, 2, 20, 2, 176))
    cmds.button(label="pre", command=do_prefix, height=18,
                backgroundColor=(0.596, 0.529, 0.769))
    cmds.text(label="")
    cmds.button(label="suf", command=do_suffix, height=18,
                backgroundColor=(0.32, 0.59, 0.72))
    cmds.text(label="")
    cmds.optionMenu("opt_increment", width=176)
    cmds.menuItem(label="_A")
    cmds.menuItem(label="1")
    cmds.menuItem(label="_1")
    cmds.menuItem(label="_01")
    cmds.menuItem(label="_001")
    cmds.menuItem(label="_0001")
    cmds.menuItem(label="_LOD_0")
    cmds.setParent(main)
    cmds.optionMenu("opt_increment", edit=True, select=4)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(110, 55))
    cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(34, 2, 36))
    cmds.button(label="_Cage", command=lambda x: add_suffix_preset("_Cage"),
                height=18, backgroundColor=(0.7, 0.6, 0.85))
    cmds.text(label="")
    cmds.button(label="_High", command=lambda x: add_suffix_preset("_High"),
                height=18, backgroundColor=(0.85, 0.7, 0.6))
    cmds.setParent("..")
    cmds.button(label="_LOW", command=lambda x: add_suffix_preset("_LOW"),
                height=18, backgroundColor=(0.6, 0.8, 0.85))
    cmds.setParent("..")
    cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
    cmds.button(label="删除首字", command=del_first_char, height=18,
                backgroundColor=(0.55, 0.55, 0.55))
    cmds.button(label="删除尾字", command=del_last_char, height=18,
                backgroundColor=(0.55, 0.55, 0.55))
    cmds.setParent("..")
    cmds.setParent(main)

    cmds.checkBox("cb_presets", label=" 更多预设", changeCommand=toggle_presets, height=18)

    cmds.frameLayout("preset_frame", labelVisible=False, borderVisible=False,
                     collapsable=False, visible=False)
    preset_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=1)
    for idx, item in enumerate(PRESET_NAMES):
        pname = item[0]
        pnote = item[1] if len(item) > 1 else ""
        note_display = " [" + pnote + "]" if pnote else ""
        cmds.rowLayout(numberOfColumns=4, columnWidth4=(28, 80, 28, 100),
                       adjustableColumn=4)
        cmds.button(label="pre", command=lambda x, p=pname: do_preset_prefix(p),
                    height=18, backgroundColor=(0.596, 0.529, 0.769), width=28)
        cmds.button(label=pname, command=lambda x, p=pname: do_preset_rename(p),
                    height=18, backgroundColor=(0.55, 0.7, 0.85), width=80)
        cmds.button(label="suf", command=lambda x, p=pname: do_preset_suffix(p),
                    height=18, backgroundColor=(0.32, 0.59, 0.72), width=28)
        cmds.text(label=note_display, align="left")
        cmds.setParent(preset_col)
    cmds.setParent(main)

    cmds.button(label="rename", command=do_rename, height=24,
                backgroundColor=(0.772, 0.521, 0.302))

    cmds.text("status_txt", label="选中模型后点击按钮操作", height=14, align="center")

    cmds.showWindow(WINDOW_NAME)


print("--- 批量重命名工具 v2.2 starting ---")
try:
    create_ui()
    print("--- 批量重命名工具 v2.2 done ---")
    debug_log("启动", "v2.2", "ready", "OK")
except Exception as e:
    import traceback
    tb = traceback.format_exc()
    print("--- 批量重命名工具 v2.2 FAILED ---")
    print(tb)
    cmds.error("重命名工具启动失败:\n" + tb)
