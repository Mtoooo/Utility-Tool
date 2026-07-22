# -*- coding: utf-8 -*-
import maya.cmds as cmds

window_name = "object_sorter_tool"

def check_same_parent(objs):
    if len(objs) <= 1:
        return True
    parents = []
    for obj in objs:
        parent = cmds.listRelatives(obj, parent=True, fullPath=True)
        parent_path = parent[0] if parent else "|"
        parents.append(parent_path)
    return len(set(parents)) == 1

def do_sort(sort_type, *args):
    sel = cmds.ls(selection=True, long=True, transforms=True)
    if not sel:
        cmds.confirmDialog(title="提示", message="请先选中要排序的物体！", button=["确定"])
        return

    if len(sel) <= 1:
        cmds.confirmDialog(title="提示", message="至少选中2个物体才能排序！", button=["确定"])
        return

    if not check_same_parent(sel):
        cmds.confirmDialog(title="提示", message="选中的物体必须在同一父级下才能排序！", button=["确定"])
        return

    reverse = cmds.checkBox("cb_reverse", q=True, value=True)
    separator = cmds.textField("tf_sep", q=True, text=True) or "_"

    def get_sort_key(obj):
        short_name = obj.split("|")[-1]
        if sort_type == "name":
            return short_name.lower()
        elif sort_type == "prefix":
            parts = short_name.split(separator)
            return parts[0].lower() if parts else short_name.lower()
        elif sort_type == "suffix":
            parts = short_name.split(separator)
            return parts[-1].lower() if parts else short_name.lower()
        else:
            return sel.index(obj)

    if sort_type == "select":
        sorted_list = sel.copy()
    else:
        sorted_list = sorted(sel, key=get_sort_key)

    if reverse:
        sorted_list = sorted_list[::-1]

    for obj in reversed(sorted_list):
        try:
            cmds.reorder(obj, front=True)
        except Exception as e:
            print(f"排序 {obj} 失败: {str(e)}")

    type_names = {
        "name": "名称",
        "prefix": "前缀",
        "suffix": "后缀",
        "select": "选中顺序"
    }
    order_text = "倒序" if reverse else "正序"
    status = f"✅ 已按{type_names[sort_type]}{order_text}排列，共{len(sel)}个物体"
    cmds.text("status_txt", edit=True, label=status)

def create_ui():
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)

    cmds.window(
        window_name,
        title="物体大纲排序工具",
        width=380,
        height=290,
        sizeable=False
    )

    main = cmds.columnLayout(adjustableColumn=True, rowSpacing=10)

    cmds.text(label="物体大纲排序工具", font="boldLabelFont", height=32, align="left")
    cmds.separator(style="double", height=4)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(170, 170))
    cmds.button(label="按名称排序", command=lambda x: do_sort("name"),
                height=35, backgroundColor=(0.2, 0.6, 0.9))
    cmds.button(label="按选中顺序", command=lambda x: do_sort("select"),
                height=35, backgroundColor=(0.2, 0.6, 0.9))
    cmds.setParent(main)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(170, 170))
    cmds.button(label="按前缀排序", command=lambda x: do_sort("prefix"),
                height=35, backgroundColor=(0.6, 0.5, 0.8))
    cmds.button(label="按后缀排序", command=lambda x: do_sort("suffix"),
                height=35, backgroundColor=(0.6, 0.5, 0.8))
    cmds.setParent(main)

    cmds.separator(height=6)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(170, 170))
    cmds.checkBox("cb_reverse", label="倒序排列", value=False)
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(60, 100))
    cmds.text(label="分隔符：", align="right")
    cmds.textField("tf_sep", text="_")
    cmds.setParent(main)
    cmds.setParent(main)

    cmds.separator(height=6)

    cmds.text(label="说明：仅对同一父级下的物体生效，排序后大纲同步更新", align="left", height=30)

    cmds.text("status_txt", label="选中物体后点击对应按钮排序", height=22, align="center")

    cmds.showWindow(window_name)

if __name__ == "__main__":
    create_ui()