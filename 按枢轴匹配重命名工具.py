# -*- coding: utf-8 -*-
import maya.cmds as cmds
import math

group_A = []
group_B = []
window_name = "pivot_match_renamer_pro"

match_result = {
    "one_to_one": [],
    "unmatched_A": [],
    "unmatched_B": [],
    "one_to_many_A": {},
    "many_to_one_B": {}
}

def get_world_pivot(obj):
    if not cmds.objExists(obj):
        return None
    try:
        pivot = cmds.xform(obj, query=True, rotatePivot=True, worldSpace=True)
        return (pivot[0], pivot[1], pivot[2])
    except:
        return None


def calc_distance(p1, p2):
    return math.sqrt(
        (p1[0] - p2[0]) ** 2 +
        (p1[1] - p2[1]) ** 2 +
        (p1[2] - p2[2]) ** 2
    )


def select_model(obj):
    if cmds.objExists(obj):
        cmds.select(obj, replace=True)


def set_group(group_type):
    global group_A, group_B
    selection = cmds.ls(selection=True, long=True, transforms=True)

    if not selection:
        cmds.confirmDialog(title=u"提示", message=u"请先选中模型！", button=[u"确定"])
        return

    display_count = len(selection)
    if group_type == "A":
        group_A = selection
        cmds.textField("tf_groupA", edit=True, text=u"A集：%d 个模型" % display_count)
    else:
        group_B = selection
        cmds.textField("tf_groupB", edit=True, text=u"B集：%d 个模型" % display_count)
    cmds.text("status_text", edit=True, label=u"已设置选择集")


def detect_matches():
    global group_A, group_B, match_result

    if not group_A or not group_B:
        cmds.confirmDialog(title=u"错误", message=u"请先设置 A集 和 B集！", button=[u"确定"])
        return

    tolerance = cmds.floatField("ff_tolerance", query=True, value=True)

    a_pivots = [(obj, get_world_pivot(obj)) for obj in group_A if get_world_pivot(obj)]
    b_pivots = [(obj, get_world_pivot(obj)) for obj in group_B if get_world_pivot(obj)]

    match_result["one_to_one"] = []
    match_result["unmatched_A"] = []
    match_result["unmatched_B"] = []
    match_result["one_to_many_A"] = {}
    match_result["many_to_one_B"] = {}

    b_match_count = {b_obj: 0 for b_obj, _ in b_pivots}
    b_match_sources = {b_obj: [] for b_obj, _ in b_pivots}
    a_match_targets = {a_obj: [] for a_obj, _ in a_pivots}

    for a_obj, a_p in a_pivots:
        matched_bs = []
        for b_obj, b_p in b_pivots:
            if calc_distance(a_p, b_p) <= tolerance:
                matched_bs.append(b_obj)
                b_match_count[b_obj] += 1
                b_match_sources[b_obj].append(a_obj)
        a_match_targets[a_obj] = matched_bs

    for a_obj, targets in a_match_targets.items():
        if len(targets) == 0:
            match_result["unmatched_A"].append(a_obj)
        elif len(targets) > 1:
            match_result["one_to_many_A"][a_obj] = targets

    for b_obj, sources in b_match_sources.items():
        if len(sources) == 0:
            match_result["unmatched_B"].append(b_obj)
        elif len(sources) > 1:
            match_result["many_to_one_B"][b_obj] = sources

    for a_obj, targets in a_match_targets.items():
        if len(targets) == 1:
            b_obj = targets[0]
            if b_match_count[b_obj] == 1:
                match_result["one_to_one"].append((a_obj, b_obj))

    update_result_ui()
    cmds.text("status_text", edit=True,
              label=u"检测完成：一对一%d组 | 未匹配A:%d | 未匹配B:%d" % (
                  len(match_result["one_to_one"]),
                  len(match_result["unmatched_A"]),
                  len(match_result["unmatched_B"])
              ))


def update_result_ui():
    cmds.setParent("result_layout")
    children = cmds.columnLayout("result_layout", query=True, childArray=True)
    if children:
        for child in children:
            cmds.deleteUI(child)

    def short_name(long_name):
        return long_name.split("|")[-1]

    cmds.text(label=u"正常配对（一对一）：%d 组" % len(match_result["one_to_one"]),
              align="left", font="smallBoldLabelFont", height=22)
    for a_obj, b_obj in match_result["one_to_one"]:
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(140, 140))
        cmds.button(label=short_name(a_obj), command=lambda x, o=a_obj: select_model(o),
                    width=135, height=22, align="left")
        cmds.button(label=short_name(b_obj), command=lambda x, o=b_obj: select_model(o),
                    width=135, height=22, align="left")
        cmds.setParent("result_layout")

    cmds.separator(height=8)

    cmds.text(label=u"未匹配的A模型：%d 个" % len(match_result["unmatched_A"]),
              align="left", font="smallBoldLabelFont", height=22, backgroundColor=(0.8, 0.3, 0.3))
    for obj in match_result["unmatched_A"]:
        cmds.button(label=short_name(obj), command=lambda x, o=obj: select_model(o),
                    width=280, height=22, align="left")

    cmds.separator(height=8)

    cmds.text(label=u"未匹配的B模型：%d 个" % len(match_result["unmatched_B"]),
              align="left", font="smallBoldLabelFont", height=22, backgroundColor=(0.8, 0.3, 0.3))
    for obj in match_result["unmatched_B"]:
        cmds.button(label=short_name(obj), command=lambda x, o=obj: select_model(o),
                    width=280, height=22, align="left")

    cmds.separator(height=8)

    cmds.text(label=u"一对多（1个A对应多个B）：%d 组" % len(match_result["one_to_many_A"]),
              align="left", font="smallBoldLabelFont", height=22, backgroundColor=(0.9, 0.7, 0.2))
    for a_obj, b_list in match_result["one_to_many_A"].items():
        cmds.button(label=u"A: %s" % short_name(a_obj), command=lambda x, o=a_obj: select_model(o),
                    width=280, height=22, align="left", backgroundColor=(0.95, 0.85, 0.5))
        for b_obj in b_list:
            cmds.button(label=u"  - %s" % short_name(b_obj), command=lambda x, o=b_obj: select_model(o),
                        width=270, height=20, align="left")

    cmds.separator(height=8)

    cmds.text(label=u"多对一（多个A对应1个B）：%d 组" % len(match_result["many_to_one_B"]),
              align="left", font="smallBoldLabelFont", height=22, backgroundColor=(0.9, 0.7, 0.2))
    for b_obj, a_list in match_result["many_to_one_B"].items():
        cmds.button(label=u"B: %s" % short_name(b_obj), command=lambda x, o=b_obj: select_model(o),
                    width=280, height=22, align="left", backgroundColor=(0.95, 0.85, 0.5))
        for a_obj in a_list:
            cmds.button(label=u"  - %s" % short_name(a_obj), command=lambda x, o=a_obj: select_model(o),
                        width=270, height=20, align="left")


def execute_rename():
    global match_result

    if not match_result["one_to_one"]:
        cmds.confirmDialog(title=u"提示",
                           message=u"没有可重命名的一对一配对模型\n请先点击检测匹配结果",
                           button=[u"确定"])
        return

    prefix_a = cmds.textField("tf_prefix_a", query=True, text=True)
    prefix_b = cmds.textField("tf_prefix_b", query=True, text=True)
    middle_name = cmds.textField("tf_middle", query=True, text=True)
    digit = cmds.intField("if_digit", query=True, value=True)

    rename_count = 0
    for index, (a_obj, b_obj) in enumerate(match_result["one_to_one"], start=1):
        index_str = ("%0" + str(digit) + "d") % index

        a_short = a_obj.split("|")[-1]
        b_short = b_obj.split("|")[-1]

        if middle_name.strip() == "":
            new_a_name = "%s%s_%s" % (prefix_a, a_short, index_str)
        else:
            new_a_name = "%s%s_%s" % (prefix_a, middle_name, index_str)

        if middle_name.strip() == "":
            new_b_name = "%s%s_%s" % (prefix_b, b_short, index_str)
        else:
            new_b_name = "%s%s_%s" % (prefix_b, middle_name, index_str)

        try:
            cmds.rename(a_obj, new_a_name)
            cmds.rename(b_obj, new_b_name)
            rename_count += 1
        except:
            continue

    cmds.text("status_text", edit=True, label=u"重命名完成：成功 %d 组" % rename_count)
    cmds.confirmDialog(title=u"完成", message=u"重命名完成！\n成功处理：%d 组模型" % rename_count, button=[u"确定"])
    detect_matches()


def create_ui():
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)

    cmds.window(
        window_name,
        title=u"枢轴配对重命名工具 增强版",
        width=420,
        height=750,
        sizeable=False
    )

    main_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnAttach=("both", 15))

    cmds.text(label=u"枢轴配对重命名工具", font="boldLabelFont", height=30)
    cmds.separator(style="double", height=5)

    cmds.text(label=u"第一步：设置A/B集", align="left", font="smallBoldLabelFont")

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(100, 280), columnAlign2=("right", "left"))
    cmds.button(label=u"设置A集", command=lambda x: set_group("A"), width=90, height=28)
    cmds.textField("tf_groupA", editable=False, text=u"A集：未选择")
    cmds.setParent(main_layout)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(100, 280), columnAlign2=("right", "left"))
    cmds.button(label=u"设置B集", command=lambda x: set_group("B"), width=90, height=28)
    cmds.textField("tf_groupB", editable=False, text=u"B集：未选择")
    cmds.setParent(main_layout)
    cmds.separator(height=5)

    cmds.text(label=u"第二步：设置枢轴容差值", align="left", font="smallBoldLabelFont")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 200))
    cmds.text(label=u"容差范围：", align="right")
    cmds.floatField("ff_tolerance", value=0.001, minValue=0.0, step=0.001)
    cmds.setParent(main_layout)
    cmds.text(label=u"（两个枢轴距离小于该值即判定为重合，单位与Maya场景一致）",
              align="left", height=18)
    cmds.separator(height=5)

    cmds.text(label=u"第三步：自定义命名规则", align="left", font="smallBoldLabelFont")

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 260))
    cmds.text(label=u"A组前缀：", align="right")
    cmds.textField("tf_prefix_a", text="AAA_")
    cmds.setParent(main_layout)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 260))
    cmds.text(label=u"B组前缀：", align="right")
    cmds.textField("tf_prefix_b", text="BBB_")
    cmds.setParent(main_layout)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 260))
    cmds.text(label=u"中间名：", align="right")
    cmds.textField("tf_middle", text="Mto")
    cmds.setParent(main_layout)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 260))
    cmds.text(label=u"序号位数：", align="right")
    cmds.intField("if_digit", value=4, minValue=1, maxValue=10)
    cmds.setParent(main_layout)
    cmds.text(label=u"（中间名留空时，将使用模型原名称作为中间部分）",
              align="left", height=18)
    cmds.separator(height=5)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 180), columnAlign2=("center", "center"))
    cmds.button(label=u"检测匹配结果", command=lambda x: detect_matches(),
                height=35, backgroundColor=(0.2, 0.6, 0.9))
    cmds.button(label=u"执行重命名", command=lambda x: execute_rename(),
                height=35, backgroundColor=(0.2, 0.8, 0.3))
    cmds.setParent(main_layout)

    cmds.text("status_text", label=u"按步骤操作，先检测再重命名", height=22, align="center")
    cmds.separator(style="double", height=5)

    cmds.text(label=u"匹配结果列表（点击模型名可直接选中）", align="left", font="smallBoldLabelFont")
    cmds.scrollLayout(width=390, height=320)
    cmds.columnLayout("result_layout", adjustableColumn=True, rowSpacing=3)
    cmds.setParent(main_layout)

    cmds.showWindow(window_name)


create_ui()
