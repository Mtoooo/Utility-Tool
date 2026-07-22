# -*- coding: utf-8 -*-
import maya.cmds as cmds
import math

window_name = "explode_grid_trigger_fix"
original_pos = {}
original_bbox_center = {}
overall_original_center = (0, 0, 0)

is_drag_intensity = False
is_drag_grid = False

def get_selected():
    return cmds.ls(selection=True, long=True, transforms=True)

def get_obj_bbox_center(obj):
    try:
        bbox = cmds.exactWorldBoundingBox(obj)
        cx = (bbox[0] + bbox[3]) / 2.0
        cy = (bbox[1] + bbox[4]) / 2.0
        cz = (bbox[2] + bbox[5]) / 2.0
        return (cx, cy, cz)
    except:
        pos = cmds.xform(obj, query=True, translation=True, worldSpace=True)
        return tuple(pos)

def init_original_data(sel):
    global original_pos, original_bbox_center, overall_original_center
    if set(original_pos.keys()) == set(sel):
        return
    
    original_pos = {}
    original_bbox_center = {}
    sum_x = sum_y = sum_z = 0.0
    
    for obj in sel:
        original_pos[obj] = cmds.xform(obj, query=True, translation=True, worldSpace=True)
        bc = get_obj_bbox_center(obj)
        original_bbox_center[obj] = bc
        sum_x += bc[0]
        sum_y += bc[1]
        sum_z += bc[2]
    
    count = len(sel)
    overall_original_center = (sum_x/count, sum_y/count, sum_z/count)

def explode_update_position():
    sel = get_selected()
    if not sel:
        return
    init_original_data(sel)
    
    intensity = cmds.floatSliderGrp("slider_intensity", query=True, value=True)
    mode = cmds.radioButtonGrp("radio_mode", query=True, select=True)
    
    for obj in sel:
        obj_cx, obj_cy, obj_cz = original_bbox_center[obj]
        dx = obj_cx - overall_original_center[0]
        dy = obj_cy - overall_original_center[1]
        dz = obj_cz - overall_original_center[2]
        
        offset_x = dx * intensity
        offset_y = dy * intensity
        offset_z = dz * intensity
        
        if mode == 2:
            offset_y = offset_z = 0
        elif mode == 3:
            offset_x = offset_z = 0
        elif mode == 4:
            offset_x = offset_y = 0
        
        ox, oy, oz = original_pos[obj]
        cmds.xform(obj, translation=(ox+offset_x, oy+offset_y, oz+offset_z), worldSpace=True)
    
    cmds.text("status_txt", edit=True, label=f"轴向炸开：{len(sel)} 个零件，倍率 {intensity:.2f}")

def explode_on_drag(*args):
    global is_drag_intensity
    is_drag_intensity = True
    explode_update_position()

def explode_on_change(*args):
    global is_drag_intensity
    
    explode_update_position()
    
    if is_drag_intensity:
        is_drag_intensity = False
        return
    
    intensity = cmds.floatSliderGrp("slider_intensity", query=True, value=True)
    current_max = cmds.floatSliderGrp("slider_intensity", query=True, maxValue=True)
    
    if intensity > 10 and current_max != 100.0:
        cmds.floatSliderGrp("slider_intensity", edit=True, maxValue=100.0, fieldMaxValue=100.0)
    elif intensity <= 0.001 and current_max != 10.0:
        cmds.floatSliderGrp("slider_intensity", edit=True, maxValue=10.0, fieldMaxValue=100.0)

def grid_update_position():
    sel = get_selected()
    if not sel:
        return
    init_original_data(sel)
    
    spacing = cmds.floatSliderGrp("slider_grid_spacing", query=True, value=True)
    count = len(sel)
    grid_size = math.ceil(count ** (1/3))
    
    for index, obj in enumerate(sel):
        x_idx = index % grid_size
        y_idx = (index // grid_size) % grid_size
        z_idx = index // (grid_size * grid_size)
        
        offset_x = (x_idx - (grid_size - 1) / 2.0) * spacing
        offset_y = (y_idx - (grid_size - 1) / 2.0) * spacing
        offset_z = (z_idx - (grid_size - 1) / 2.0) * spacing
        
        target_cx = overall_original_center[0] + offset_x
        target_cy = overall_original_center[1] + offset_y
        target_cz = overall_original_center[2] + offset_z
        
        ox, oy, oz = original_pos[obj]
        bcx, bcy, bcz = original_bbox_center[obj]
        new_x = target_cx - (bcx - ox)
        new_y = target_cy - (bcy - oy)
        new_z = target_cz - (bcz - oz)
        
        cmds.xform(obj, translation=(new_x, new_y, new_z), worldSpace=True)
    
    cmds.text("status_txt", edit=True, label=f"点阵排列：{count} 个零件，{grid_size}×{grid_size}×{grid_size}，间距 {spacing:.1f}")

def grid_on_drag(*args):
    global is_drag_grid
    is_drag_grid = True
    grid_update_position()

def grid_on_change(*args):
    global is_drag_grid
    
    grid_update_position()
    
    if is_drag_grid:
        is_drag_grid = False
        return
    
    spacing = cmds.floatSliderGrp("slider_grid_spacing", query=True, value=True)
    current_max = cmds.floatSliderGrp("slider_grid_spacing", query=True, maxValue=True)
    
    if spacing > 20 and current_max != 100.0:
        cmds.floatSliderGrp("slider_grid_spacing", edit=True, maxValue=100.0, fieldMaxValue=100.0)
    elif spacing <= 0.1 and current_max != 20.0:
        cmds.floatSliderGrp("slider_grid_spacing", edit=True, maxValue=20.0, fieldMaxValue=100.0)

def reset_positions():
    global original_pos, original_bbox_center
    if not original_pos:
        cmds.confirmDialog(title="提示", message="没有可还原的位置记录！", button=["确定"])
        return
    
    for obj, pos in original_pos.items():
        if cmds.objExists(obj):
            cmds.xform(obj, translation=pos, worldSpace=True)
    
    original_pos = {}
    original_bbox_center = {}
    cmds.floatSliderGrp("slider_intensity", edit=True, value=0.0, maxValue=10.0, fieldMaxValue=100.0)
    cmds.floatSliderGrp("slider_grid_spacing", edit=True, value=5.0, maxValue=20.0, fieldMaxValue=100.0)
    cmds.text("status_txt", edit=True, label="已还原所有零件到原始位置")

def create_ui():
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)
    
    cmds.window(
        window_name,
        title="爆炸与点阵排列工具",
        width=420,
        height=400,
        sizeable=False
    )
    
    main = cmds.columnLayout(adjustableColumn=True, rowSpacing=12, columnAttach=("both", 18))
    
    cmds.text(label="爆炸视图 / 点阵排列工具", font="boldLabelFont", height=32, align="left")
    cmds.separator(style="double", height=4)
    
    cmds.text(label="🔹 轴向爆炸", align="left", font="smallBoldLabelFont")
    
    cmds.floatSliderGrp(
        "slider_intensity",
        label="扩散强度",
        field=True,
        minValue=0.0,
        maxValue=10.0,
        fieldMinValue=0.0,
        fieldMaxValue=100.0,
        value=0.0,
        step=0.1,
        columnWidth3=(80, 70, 230),
        changeCommand=explode_on_change,
        dragCommand=explode_on_drag
    )
    
    cmds.radioButtonGrp(
        "radio_mode",
        label="散开轴向",
        labelArray4=["三轴同时", "仅X轴", "仅Y轴", "仅Z轴"],
        numberOfRadioButtons=4,
        select=1,
        columnWidth5=(80, 80, 80, 80, 80),
        changeCommand=explode_on_change
    )
    
    cmds.button(
        label="应用轴向爆炸",
        command=explode_on_change,
        height=32,
        backgroundColor=(0.9, 0.5, 0.2)
    )
    
    cmds.separator(style="double", height=8)
    
    cmds.text(label="🔹 正方体点阵排列", align="left", font="smallBoldLabelFont")
    
    cmds.floatSliderGrp(
        "slider_grid_spacing",
        label="点阵间距",
        field=True,
        minValue=0.5,
        maxValue=20.0,
        fieldMinValue=0.1,
        fieldMaxValue=100.0,
        value=5.0,
        step=0.2,
        columnWidth3=(80, 70, 230),
        changeCommand=grid_on_change,
        dragCommand=grid_on_drag
    )
    
    cmds.button(
        label="排列成正方体点阵",
        command=grid_on_change,
        height=32,
        backgroundColor=(0.3, 0.7, 0.4)
    )
    
    cmds.separator(height=6)
    
    cmds.button(
        label="还原原始位置",
        command=lambda x: reset_positions(),
        height=36,
        backgroundColor=(0.5, 0.5, 0.6)
    )
    
    cmds.text(
        label="💡 滑块默认10，输入>10自动解锁100，输入0复位短行程",
        align="left",
        height=25
    )
    
    cmds.text("status_txt", label="选中零件后拖动滑块调整", height=22, align="center")
    
    cmds.showWindow(window_name)

if __name__ == "__main__":
    create_ui()