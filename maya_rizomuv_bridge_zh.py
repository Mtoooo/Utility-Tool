# -*- coding: utf-8 -*-
"""
RizomUV <> Maya Bridge v5.2 (OBJ - 顶点计数和UV修复版)
- Pure OBJ pipeline: per-mesh export -> clean merge -> RizomUV
- UV retrieval: direct OBJ parsing + OpenMaya API UV write
- Supports 50+ models
- Bilingual UI (zh / en)

v5.2 修复版：
  修复1：RizomUV 把 v/vt 放在 g 头之前 → 解析器跳过所有顶点和UV
         → 改为全局累积 v/vt，再按面索引回填每 group 的顶点和UV数
  修复2：assignUVs 用显式 MIntArray 代替 Python list，防止类型不匹配
         → 同时显式指定 currentUVSetName，防止写到错误 UV set
"""

import maya.cmds as cmds
import maya.OpenMayaUI as omui
import maya.api.OpenMaya as omapi
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
import subprocess
import os
import platform
import sys
import locale
import logging
import json
import tempfile
import time
from pathlib import Path

# ── 全局 ───────────────────────────────────────────
panel_instance = None
logger = logging.getLogger("RizomBridge")

# ── PySide 兼容 ───────────────────────────────────
try:
    if sys.version_info.major >= 3 and sys.version_info.minor >= 11:
        try:
            from PySide6 import QtWidgets, QtCore
            from shiboken6 import wrapInstance
            print("RizomBridge: Using PySide6")
        except ImportError:
            from PySide2 import QtWidgets, QtCore
            from shiboken2 import wrapInstance
            print("RizomBridge: Using PySide2")
    else:
        from PySide2 import QtWidgets, QtCore
        from shiboken2 import wrapInstance
        print("RizomBridge: Using PySide2")
except ImportError as _e:
    raise ImportError("RizomBridge: PySide not found: %s" % _e) from _e

# ── 常量 ───────────────────────────────────────────
INSTALL_SUBDIR = "RZMUV"
CONFIG_FILE = "settings.json"
LUA_SCRIPT_FILE = "rizomuv_control.lua"
OBJ_FILE = "RizomUVMayaBridge.obj"
CACHE_FILE = "export_cache.json"
WORKSPACE_CTRL = "rizomUVBridgeWorkspaceControl"

DEFAULT_RIZOM_PATH = {
    "Windows": "C:\\Program Files\\Rizom Lab\\RizomUV 2024.0\\rizomuv.exe",
    "Darwin": "/Applications/RizomUV 2024.1.app",
    "Linux": "/usr/local/bin/rizomuv",
}

TEXT = {
    "zh": {
        "title": "RizomUV <> Maya 桥接 v5.2",
        "settings": "设置",
        "path": "RizomUV 路径：",
        "carry_uv": "携带现有 UV 发送",
        "send": "发送选择到 RizomUV",
        "get": "从 RizomUV 取回 UV",
        "ready": "就绪",
        "no_mesh": "错误：没有选中网格物体。",
        "preparing": "正在准备数据...",
        "exporting": "正在导出 OBJ...",
        "export_fail": "错误：OBJ 导出失败。",
        "launching": "正在启动 RizomUV...",
        "sent": "已发送到 RizomUV。编辑 UV 后按 Ctrl+S 保存，回 Maya 点「取回 UV」。",
        "importing": "正在导入 UV...",
        "no_target": "错误：没有选中目标物体。",
        "no_obj": "错误：找不到 OBJ 文件。请先在 RizomUV 中 Ctrl+S 保存。",
        "import_fail": "错误：OBJ 导入失败。",
        "no_geo": "错误：导入的 OBJ 中没有几何体。",
        "path_invalid": "错误：RizomUV 路径无效。",
        "launch_fail": "启动 RizomUV 失败：",
        "path_updated": "RizomUV 路径已更新。",
        "path_error": "浏览路径时出错。",
        "uv_done": "个物体 UV 已导入。",
        "uv_partial": "UV 导入：成功 {}/{}，失败 {}。",
        "uv_fail": "个物体 UV 导入失败（错误：{}）。",
        "debug": "调试",
    },
    "en": {
        "title": "RizomUV <> Maya Bridge v5.2",
        "settings": "Settings",
        "path": "RizomUV Path:",
        "carry_uv": "Send With Existing UVs",
        "send": "Send Selection to RizomUV",
        "get": "Get UVs from RizomUV",
        "ready": "Ready",
        "no_mesh": "Error: No meshes selected.",
        "preparing": "Preparing data...",
        "exporting": "Exporting OBJ...",
        "export_fail": "Error: OBJ export failed.",
        "launching": "Launching RizomUV...",
        "sent": "Sent to RizomUV. Ctrl+S in RizomUV, then click Get UVs in Maya.",
        "importing": "Importing UVs...",
        "no_target": "Error: No target objects selected.",
        "no_obj": "Error: OBJ file not found. Save in RizomUV (Ctrl+S) first.",
        "import_fail": "Error: OBJ import failed.",
        "no_geo": "Error: No geometry in imported OBJ.",
        "path_invalid": "Error: Invalid RizomUV path.",
        "launch_fail": "Failed to start RizomUV: ",
        "path_updated": "RizomUV path updated.",
        "path_error": "Error during file browse.",
        "uv_done": " object(s) UVs imported.",
        "uv_partial": "UV Import: {}/{} succeeded. Errors: {}.",
        "uv_fail": " objects UV import failed (errors: {}).",
        "debug": "DEBUG",
    },
}


def setup_logging(level=logging.ERROR):
    if not logger.handlers:
        logger.setLevel(level)
        fmt = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        )
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(fmt)
        logger.addHandler(ch)
        logger.propagate = False
    else:
        logger.setLevel(level)


setup_logging(level=logging.ERROR)


# ── 配置 ───────────────────────────────────────────
class ConfigManager(object):
    def __init__(self):
        self.base_dir = self._base_dir()
        self.config_path = self.base_dir / CONFIG_FILE
        self.lua_path = self.base_dir / LUA_SCRIPT_FILE
        self.obj_path = self.base_dir / OBJ_FILE
        self.cache_path = self.base_dir / CACHE_FILE
        self.rizom_path = DEFAULT_RIZOM_PATH.get(platform.system(), "")
        self.carry_uv = True
        self.log_level = "ERROR"
        self.language = "zh"
        self._ensure_dir()
        self._load_or_create()

    def _base_dir(self):
        try:
            return Path(cmds.internalVar(userScriptDir=True)) / INSTALL_SUBDIR
        except Exception:
            return Path(os.path.expanduser("~")) / ".maya_rizom" / INSTALL_SUBDIR

    def _ensure_dir(self):
        if not self.base_dir.exists():
            try:
                self.base_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

    def _load_or_create(self):
        if not self.config_path.is_file():
            self._save()
            return
        try:
            with open(str(self.config_path), "r", encoding="utf-8") as f:
                d = json.load(f)
            self.rizom_path = d.get("rizomPath", self.rizom_path)
            self.carry_uv = d.get("carryUV", self.carry_uv)
            lvl = d.get("logLevel", "ERROR").upper()
            if lvl in ("INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"):
                self.log_level = lvl
            self.language = d.get("language", "zh")
        except Exception:
            self._save()

    def _save(self):
        data = {
            "rizomPath": str(self.rizom_path),
            "carryUV": self.carry_uv,
            "logLevel": self.log_level,
            "language": self.language,
        }
        try:
            self._ensure_dir()
            with open(str(self.config_path), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except IOError:
            return False

    def save(self):
        return self._save()


try:
    config = ConfigManager()
except Exception as _e:
    raise RuntimeError("RizomBridge: Config init failed: %s" % _e) from _e


# ── 工具函数 ───────────────────────────────────────
def short_name(obj):
    return obj.split("|")[-1]


def get_mesh_shape(transform_obj):
    """返回 transform 下第一个非中间 mesh shape，或 None"""
    shapes = cmds.listRelatives(transform_obj, s=True, f=True, type="mesh") or []
    for s in shapes:
        if not cmds.objExists(s):
            continue
        try:
            if cmds.getAttr(s + ".intermediateObject"):
                continue
        except Exception:
            pass
        return s
    return None


def mesh_stats(shape):
    try:
        return cmds.polyEvaluate(shape, vertex=True), cmds.polyEvaluate(shape, face=True)
    except Exception:
        return None, None


def face_vert_total(shape):
    try:
        return cmds.polyEvaluate(shape, totalVertexFace=True)
    except Exception:
        return None


def filter_meshes(selection):
    """从选择中筛选含 mesh 的 transform"""
    result = []
    for item in selection:
        shapes = cmds.listRelatives(item, s=True, f=True, type="mesh", ni=True) or []
        if shapes:
            result.append(item)
    return result


def collect_meshes_from_nodes(node_list):
    """
    从节点列表中收集所有带 mesh 的 transform。
    包括：列表中直接的 mesh transform + 列表中组节点的后代 mesh transform
    返回 mesh info 列表
    """
    results = []
    seen = set()

    for node in node_list:
        if not cmds.objExists(node):
            continue
        full = cmds.ls(node, long=True)
        if not full:
            continue
        node = full[0]

        # 递归找所有后代 transform（包括自己）
        all_transforms = []
        nt = cmds.nodeType(node)
        if nt == "transform":
            all_transforms.append(node)
        try:
            children = cmds.listRelatives(node, ad=True, type="transform", f=True) or []
            all_transforms.extend(children)
        except Exception:
            pass

        for t in all_transforms:
            if t in seen:
                continue
            seen.add(t)
            if not cmds.objExists(t):
                continue
            shape = get_mesh_shape(t)
            if shape:
                v, f = mesh_stats(shape)
                fvt = face_vert_total(shape)
                results.append({
                    "node": t, "shape": shape, "name": short_name(t),
                    "verts": v, "faces": f, "faceVertTotal": fvt,
                    "used": False,
                })

    return results


def safe_delete_nodes(node_list):
    """安全删除节点列表"""
    deleted = 0
    # 先解锁
    for n in node_list:
        if cmds.objExists(n):
            try:
                cmds.lockNode(n, lock=False)
            except Exception:
                pass
    # 删除 shape 节点
    for n in node_list:
        if cmds.objExists(n) and cmds.nodeType(n) != "transform":
            try:
                cmds.delete(n)
                deleted += 1
            except Exception:
                pass
    # 删除 transform 节点
    for n in node_list:
        if cmds.objExists(n):
            try:
                cmds.delete(n)
                deleted += 1
            except Exception:
                pass
    logger.info("Deleted %d imported nodes" % deleted)


# ── OBJ 解析器（v5.2 核心：绕过 Maya 导入，直接读 UV 数据）──
def parse_obj_groups(path):
    """
    解析 RizomUV 保存的 OBJ 文件，提取每个 group 的 UV 数据和拓扑信息。
    v5.2: v/vt 全局累积（因为 RizomUV 把它们放在 g 头之前）。
    
    返回: [{name, verts, faces, faceVertTotal, uvs, uvPerFace, uvIds}]
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    all_vt = {}        # 全局: 1-based vt索引 -> (u, v)
    all_v = []         # 全局: 1-based v索引 -> "v x y z" 行
    groups = []
    cur = None

    for line in lines:
        line = line.strip()
        if not line or line[0] == "#":
            continue
        parts = line.split()
        if not parts:
            continue

        cmd = parts[0]

        if cmd == "g":
            if cur and cur["faces"] > 0:
                groups.append(cur)
            name = " ".join(parts[1:]) if len(parts) > 1 else "default"
            cur = {
                "name": name,
                "verts": 0, "faces": 0, "faceVertTotal": 0,
                "uvs": [], "uvPerFace": [], "uvIds": [],
                "_vset": set(), "_raw_vt": [],
            }

        elif cmd == "vt":
            # 全局累积（不管是否在 g 内，因为 RizomUV 把 vt 放在 g 之前）
            if len(parts) >= 3:
                idx = len(all_vt) + 1
                all_vt[idx] = (float(parts[1]), float(parts[2]))

        elif cmd == "v":
            # 全局累积（同理）
            all_v.append(line)

        elif cmd == "f" and cur is not None:
            nv = len(parts) - 1
            # 收集此面用到的顶点索引（用于 v5.2 全局回填）
            v_indices = []
            ft_uvs = []
            for vs in parts[1:]:
                comps = vs.split("/")
                vi = int(comps[0]) if comps[0] else 0
                vt = int(comps[1]) if len(comps) >= 2 and comps[1] else 0
                v_indices.append(vi)
                ft_uvs.append(vt)
            cur["faces"] += 1
            cur["faceVertTotal"] += nv
            cur["uvPerFace"].append(nv)
            cur["_raw_vt"].extend(ft_uvs)
            # v5.2: 用顶点索引从全局 all_v 回填 group 的 _vset
            for vi in v_indices:
                if 1 <= vi <= len(all_v):
                    cur["_vset"].add(all_v[vi - 1])

    if cur and cur["faces"] > 0:
        groups.append(cur)

    # 后处理
    for grp in groups:
        grp["verts"] = len(grp.pop("_vset", set()) or set())
        raw = grp.pop("_raw_vt", [])
        used = sorted(set(vt for vt in raw if vt > 0))
        local_map = {}
        grp["uvs"] = []
        for vt_i in used:
            local_map[vt_i] = len(grp["uvs"])
            grp["uvs"].append(all_vt.get(vt_i, (0.0, 0.0)))
        grp["uvIds"] = [local_map.get(vt, 0) for vt in raw]

    return groups


def write_uvs_to_mesh(mesh_shape, uv_list, uv_per_face, uv_ids):
    """
    用 OpenMaya API 直接将 UV 写入 mesh。
    v5.2: 用显式 MIntArray + currentUVSetName，防止类型不匹配和 UV set 错误。
    """
    sel = omapi.MSelectionList()
    sel.add(mesh_shape)
    dag = sel.getDagPath(0)
    mesh_fn = omapi.MFnMesh(dag)

    # 获取当前 UV set 名称
    uv_set = mesh_fn.currentUVSetName()

    u_ary = omapi.MFloatArray()
    v_ary = omapi.MFloatArray()
    for u_val, v_val in uv_list:
        u_ary.append(float(u_val))
        v_ary.append(float(v_val))

    mesh_fn.clearUVs(uv_set)
    mesh_fn.setUVs(u_ary, v_ary, uv_set)

    # v5.2: 显式 MIntArray（避免 Python list → Maya API 类型转换问题）
    uv_count_ary = omapi.MIntArray()
    for c in uv_per_face:
        uv_count_ary.append(int(c))
    uv_id_ary = omapi.MIntArray()
    for i in uv_ids:
        uv_id_ary.append(int(i))

    mesh_fn.assignUVs(uv_count_ary, uv_id_ary, uv_set)
    return True


def copy_uvs_api(src_shape, dst_shape):
    """
    用 OpenMaya API 从源 mesh 复制 UV 到目标 mesh（回退路径用）。
    比 polyTransfer 快，因为绕过 Maya 命令层。
    """
    # 读源 UV
    sel_src = omapi.MSelectionList()
    sel_src.add(src_shape)
    src_mesh = omapi.MFnMesh(sel_src.getDagPath(0))
    u_ary, v_ary = src_mesh.getUVs()
    uv_counts, uv_ids = src_mesh.getAssignedUVs()

    # 写目标 UV
    sel_dst = omapi.MSelectionList()
    sel_dst.add(dst_shape)
    dst_mesh = omapi.MFnMesh(sel_dst.getDagPath(0))
    dst_mesh.clearUVs()
    dst_mesh.setUVs(u_ary, v_ary)
    dst_mesh.assignUVs(uv_counts, uv_ids)
    return True


# ── OBJ 导出（逐个 → 干净合并）────────────────────
def export_clean_obj(selected_items, output_path):
    """
    逐个导出每个网格 → 合并为干净的 OBJ。
    正确处理 v/vt/vn 索引偏移。
    返回 (count, export_info_list) — info 按导出顺序排列
    """
    temp_dir = Path(tempfile.gettempdir()) / "rzmuv_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(output_path)

    temp_files = []
    export_info = []
    count = 0

    for i, item in enumerate(selected_items):
        name = short_name(item)
        tmp = temp_dir / ("_rzm_%04d.obj" % i)
        try:
            cmds.select(item, replace=True)
            cmds.file(
                str(tmp),
                force=True,
                options="groups=0;ptgroups=0;materials=0;smoothing=0;normals=1",
                type="OBJexport",
                exportSelected=True,
                preserveReferences=False,
            )
            if tmp.exists():
                temp_files.append((tmp, name))
                shape = get_mesh_shape(item)
                v, f = mesh_stats(shape) if shape else (None, None)
                fvt = face_vert_total(shape) if shape else None
                export_info.append({
                    "name": name, "index": i,
                    "verts": v, "faces": f, "faceVertTotal": fvt,
                })
                count += 1
        except Exception as e:
            logger.error("Export failed: %s -> %s" % (name, e))

    if count == 0:
        return 0, []

    v_off = 0
    vt_off = 0
    vn_off = 0
    parts = []

    for tmp_path, name in temp_files:
        try:
            with open(str(tmp_path), "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            continue

        verts = []
        uvs = []
        normals = []
        faces = []

        for line in lines:
            s = line.strip()
            if s.startswith("v "):
                verts.append(s)
            elif s.startswith("vt "):
                uvs.append(s)
            elif s.startswith("vn "):
                normals.append(s)
            elif s.startswith("f "):
                tokens = s[2:].split()
                new_tokens = []
                for tok in tokens:
                    idx = tok.split("/")
                    ni = []
                    if idx[0]:
                        ni.append(str(int(idx[0]) + v_off))
                    else:
                        ni.append("")
                    if len(idx) > 1:
                        if idx[1]:
                            ni.append(str(int(idx[1]) + vt_off))
                        else:
                            ni.append("")
                    if len(idx) > 2:
                        if idx[2]:
                            ni.append(str(int(idx[2]) + vn_off))
                        else:
                            ni.append("")
                    new_tokens.append("/".join(ni))
                faces.append("f " + " ".join(new_tokens))

        parts.append({"name": name, "v": verts, "vt": uvs, "vn": normals, "f": faces})
        v_off += len(verts)
        vt_off += len(uvs)
        vn_off += len(normals)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(output_path), "w", encoding="utf-8") as f:
        f.write("# RizomUV Maya Bridge v5.2\n")
        f.write("# %d objects\n\n" % len(parts))
        for p in parts:
            f.write("g %s\n" % p["name"])
            f.write("o %s\n" % p["name"])
            for v in p["v"]:
                f.write(v + "\n")
            for vt in p["vt"]:
                f.write(vt + "\n")
            for vn in p["vn"]:
                f.write(vn + "\n")
            for fc in p["f"]:
                f.write(fc + "\n")
            f.write("\n")

    for tmp_path, _ in temp_files:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    logger.info("Exported %d meshes to: %s" % (len(parts), output_path))
    return len(parts), export_info


# ── 主面板 ─────────────────────────────────────────
class BridgePanel(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(BridgePanel, self).__init__(parent)
        self.setObjectName("rizomUVBridgePanel")
        self._alive = True
        self._jobs = []
        self._export_cache = []
        self._build_ui()
        self._connect_signals()
        self._update_lang()
        self.destroyed.connect(self._on_destroyed)
        lvl = getattr(logging, config.log_level, logging.ERROR)
        setup_logging(level=lvl)
        logger.info("RizomUV Bridge Panel v5.2 initialized.")

    def _on_destroyed(self):
        self._alive = False
        self._kill_jobs()

    def tr(self, key):
        return TEXT.get(config.language, TEXT["zh"]).get(key, key)

    # ── UI ───────────────────────────────────────
    def _build_ui(self):
        main = QtWidgets.QVBoxLayout(self)
        main.setSpacing(6)
        main.setContentsMargins(8, 8, 8, 8)

        self.grp_set = QtWidgets.QGroupBox()
        set_lay = QtWidgets.QVBoxLayout()
        path_row = QtWidgets.QHBoxLayout()
        self.lbl_path = QtWidgets.QLabel()
        path_row.addWidget(self.lbl_path)
        self.edt_path = QtWidgets.QLineEdit(config.rizom_path)
        path_row.addWidget(self.edt_path, 1)
        self.btn_browse = QtWidgets.QPushButton("...")
        self.btn_browse.setFixedWidth(30)
        path_row.addWidget(self.btn_browse)
        set_lay.addLayout(path_row)
        self.grp_set.setLayout(set_lay)
        main.addWidget(self.grp_set)

        self.chk_carry = QtWidgets.QCheckBox()
        self.chk_carry.setChecked(config.carry_uv)
        main.addWidget(self.chk_carry)

        self.btn_send = QtWidgets.QPushButton()
        main.addWidget(self.btn_send)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        main.addWidget(sep)

        self.btn_get = QtWidgets.QPushButton()
        main.addWidget(self.btn_get)

        self.lbl_status = QtWidgets.QLabel()
        self.lbl_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True)
        main.addWidget(self.lbl_status)

        main.addStretch()

        bottom = QtWidgets.QHBoxLayout()
        self.btn_lang = QtWidgets.QPushButton()
        self.btn_lang.setFixedWidth(40)
        bottom.addWidget(self.btn_lang)
        bottom.addStretch()
        self.btn_debug = QtWidgets.QPushButton()
        self.btn_debug.setCheckable(True)
        bottom.addWidget(self.btn_debug)
        main.addLayout(bottom)

    def _connect_signals(self):
        self.btn_send.clicked.connect(self.do_send)
        self.btn_get.clicked.connect(self.do_get)
        self.chk_carry.toggled.connect(self._on_setting_changed)
        self.edt_path.editingFinished.connect(self._on_setting_changed)
        self.btn_browse.clicked.connect(self.browse_rizom)
        self.btn_lang.clicked.connect(self.toggle_lang)
        self.btn_debug.toggled.connect(self.toggle_debug)
        self._register_jobs()

    def _register_jobs(self):
        self._kill_jobs()
        try:
            j = cmds.scriptJob(
                event=["SelectionChanged", self._safe_refresh],
                parent=self.objectName(),
                protected=True,
            )
            self._jobs.append(j)
        except Exception:
            pass

    def _kill_jobs(self):
        for j in self._jobs:
            try:
                if cmds.scriptJob(exists=j):
                    cmds.scriptJob(kill=j, force=True)
            except Exception:
                pass
        self._jobs = []

    def _safe_refresh(self):
        if not self._alive:
            return

    def _on_setting_changed(self):
        config.rizom_path = self.edt_path.text()
        config.carry_uv = self.chk_carry.isChecked()
        config.save()

    def toggle_lang(self):
        config.language = "en" if config.language == "zh" else "zh"
        config.save()
        self._update_lang()

    def toggle_debug(self, checked):
        if checked:
            logger.setLevel(logging.INFO)
            config.log_level = "INFO"
            self.btn_debug.setText(self.tr("debug"))
            logger.info("Debug mode ON")
        else:
            logger.setLevel(logging.ERROR)
            config.log_level = "ERROR"
            self.btn_debug.setText("\u26a1")
        config.save()

    def _update_lang(self):
        if not self._alive:
            return
        self.setWindowTitle(self.tr("title"))
        self.grp_set.setTitle(self.tr("settings"))
        self.lbl_path.setText(self.tr("path"))
        self.chk_carry.setText(self.tr("carry_uv"))
        self.btn_send.setText(self.tr("send"))
        self.btn_get.setText(self.tr("get"))
        self.lbl_status.setText(self.tr("ready"))
        self.btn_lang.setText("EN" if config.language == "zh" else "ZH")
        is_dbg = config.log_level == "INFO"
        self.btn_debug.setChecked(is_dbg)
        self.btn_debug.setText(self.tr("debug") if is_dbg else "\u26a1")

    def _set_status(self, msg, level="info"):
        color = {"info": "white", "warning": "orange", "error": "#ff6666"}.get(level, "white")
        try:
            self.lbl_status.setStyleSheet("color: %s;" % color)
            self.lbl_status.setText(msg)
        except RuntimeError:
            pass
        if level == "info":
            logger.info(msg)
        elif level == "warning":
            logger.warning(msg)
        elif level == "error":
            logger.error(msg)

    def browse_rizom(self):
        system = platform.system()
        start = ""
        if config.rizom_path:
            start = str(Path(config.rizom_path).parent)
        if not start or not Path(start).exists():
            if system == "Windows":
                start = "C:\\Program Files"
            elif system == "Darwin":
                start = "/Applications"
            else:
                start = "/usr/bin" if Path("/usr/bin").exists() else "/"
        try:
            if system == "Darwin":
                path = QtWidgets.QFileDialog.getExistingDirectory(
                    self, "Locate RizomUV .app", start,
                    QtWidgets.QFileDialog.Option.ShowDirsOnly,
                )
            else:
                flt = "Executables (*.exe)" if system == "Windows" else "Executables (*)"
                tup = QtWidgets.QFileDialog.getOpenFileName(self, "Locate RizomUV", start, flt)
                path = tup[0] if isinstance(tup, tuple) else ""
            if path:
                p = Path(path)
                valid = False
                if system == "Darwin" and p.is_dir() and p.suffix == ".app":
                    valid = True
                elif system == "Windows" and p.is_file() and p.suffix.lower() == ".exe":
                    valid = True
                elif p.is_file() and os.access(str(p), os.X_OK):
                    valid = True
                if valid:
                    config.rizom_path = str(p)
                    self.edt_path.setText(str(p))
                    config.save()
                    self._set_status(self.tr("path_updated"), "info")
                else:
                    cmds.warning("Invalid path: %s" % p)
        except Exception:
            self._set_status(self.tr("path_error"), "error")

    # ── 发送 ─────────────────────────────────────
    def do_send(self):
        self._set_status(self.tr("preparing"), "info")

        orig_sel = cmds.ls(selection=True, long=True) or []

        sel = cmds.ls(selection=True, long=True, type="transform") or []
        meshes = filter_meshes(sel)
        if not meshes:
            self._set_status(self.tr("no_mesh"), "error")
            return

        # 验证路径
        system = platform.system()
        rp = Path(config.rizom_path)
        valid = False
        if system == "Darwin":
            if config.rizom_path.endswith(".app") and rp.is_dir():
                valid = True
            elif rp.is_file() and os.access(config.rizom_path, os.X_OK):
                valid = True
        elif system == "Windows":
            if rp.is_file() and rp.suffix.lower() == ".exe":
                valid = True
        elif rp.is_file() and os.access(config.rizom_path, os.X_OK):
            valid = True
        if not valid:
            self._set_status(self.tr("path_invalid"), "error")
            cmds.select(orig_sel, replace=True)
            return

        # 导出
        self._set_status(self.tr("exporting"), "info")
        try:
            cnt, info = export_clean_obj(meshes, Path(config.obj_path))
            if cnt == 0:
                self._set_status(self.tr("export_fail"), "error")
                cmds.select(orig_sel, replace=True)
                return
        except Exception as e:
            self._set_status(self.tr("export_fail") + " " + str(e), "error")
            cmds.select(orig_sel, replace=True)
            return

        # 保存缓存（按导出顺序）
        self._export_cache = info
        try:
            with open(str(config.cache_path), "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # Lua 脚本
        obj_p = str(config.obj_path).replace("\\", "/")
        flag = "XYZUVW=true" if self.chk_carry.isChecked() else "XYZ=true"
        lua = (
            "-- RizomUV Maya Bridge v5.2 --\n"
            "ZomLoad({File={Path=\"%s\", ImportGroups=true, %s}, NormalizeUVW=false})\n"
        ) % (obj_p, flag)

        try:
            with open(str(config.lua_path), "w", encoding="utf-8") as f:
                f.write(lua)
        except IOError:
            self._set_status("Error writing Lua script.", "error")
            cmds.select(orig_sel, replace=True)
            return

        # 启动
        self._set_status(self.tr("launching"), "info")
        try:
            if system == "Windows":
                subprocess.Popen(
                    [config.rizom_path, "-cfi", str(config.lua_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    text=True, encoding=locale.getpreferredencoding(False),
                )
            elif system == "Darwin":
                subprocess.Popen([
                    "open", "-a", config.rizom_path,
                    "--args", "-cfi", str(config.lua_path),
                ])
            else:
                subprocess.Popen(
                    [config.rizom_path, "-cfi", str(config.lua_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding=locale.getpreferredencoding(False),
                )
            self._set_status(self.tr("sent"), "info")
        except Exception as e:
            self._set_status(self.tr("launch_fail") + str(e), "error")

        cmds.select(orig_sel, replace=True)

    # ── 取回（v5.2：OBJ 解析 + 回退导入）──
    def do_get(self):
        """
        v5.2 取回核心逻辑：
        快速路径：OBJ 有 group → 解析 OBJ + API 直写 UV
        回退路径：OBJ 无 group → 导入 OBJ + mesh 差集 + API 复制 UV
        """
        t0 = time.time()
        self._set_status(self.tr("importing"), "info")

        # ── Step 1: 构建目标列表 ──
        orig_sel = cmds.ls(selection=True, long=True) or []
        target_transforms = filter_meshes(
            cmds.ls(selection=True, long=True, type="transform") or []
        )
        if not target_transforms:
            self._set_status(self.tr("no_target"), "error")
            return

        targets = []
        use_cache = False
        cache_data = []
        if config.cache_path.is_file():
            try:
                with open(str(config.cache_path), "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
            except Exception:
                cache_data = []
        if not cache_data and self._export_cache:
            cache_data = self._export_cache

        if cache_data and len(cache_data) == len(target_transforms):
            first_name = short_name(target_transforms[0])
            cache_first = cache_data[0].get("name", "")
            if first_name == cache_first or cache_data[0].get("verts"):
                use_cache = True
                for i, t in enumerate(target_transforms):
                    shape = get_mesh_shape(t)
                    if not shape:
                        use_cache = False
                        break
                    ci = cache_data[i]
                    targets.append({
                        "node": t, "shape": shape, "name": short_name(t),
                        "verts": ci.get("verts"),
                        "faces": ci.get("faces"),
                        "faceVertTotal": ci.get("faceVertTotal"),
                        "used": False,
                    })

        if not use_cache:
            for t in target_transforms:
                shape = get_mesh_shape(t)
                if not shape:
                    continue
                v, f = mesh_stats(shape)
                fvt = face_vert_total(shape)
                targets.append({
                    "node": t, "shape": shape, "name": short_name(t),
                    "verts": v, "faces": f, "faceVertTotal": fvt,
                    "used": False,
                })

        if not targets:
            self._set_status(self.tr("no_target"), "error")
            return

        logger.info("Targets: %d objects (cached=%s, %.3fs)" % (
            len(targets), use_cache, time.time() - t0
        ))

        # ── Step 2: 检查 OBJ ──
        obj_p = Path(config.obj_path)
        if not obj_p.is_file():
            self._set_status(self.tr("no_obj"), "error")
            cmds.select(orig_sel, replace=True)
            return
        logger.info("OBJ file: %s (%d bytes)" % (obj_p, obj_p.stat().st_size))

        # ── Step 3: 尝试解析 OBJ groups ──
        t_parse = time.time()
        obj_groups = []
        try:
            obj_groups = parse_obj_groups(str(obj_p))
        except Exception as e:
            logger.warning("OBJ parse error: %s" % e)
        logger.info("Parsed %d OBJ groups (%.3fs)" % (len(obj_groups), time.time() - t_parse))

        # ── Step 4: 根据有无 group 选路径 ──
        if obj_groups:
            # ===== 快速路径：解析 OBJ + API 直写 =====
            logger.info("=== FAST PATH: OBJ parse + API write ===")
            self._do_get_fast(obj_groups, targets, t0, orig_sel)
        else:
            # ===== 回退路径：导入 OBJ + mesh 差集 + API 复制 =====
            logger.info("=== FALLBACK: Import OBJ + mesh diff + API copy ===")
            self._do_get_fallback(targets, obj_p, t0, orig_sel)

    # ── 快速路径 ──
    def _do_get_fast(self, obj_groups, targets, t0, orig_sel):
        for g in obj_groups:
            logger.info("  [%s]  v=%d  f=%d  fvt=%d  uvs=%d" % (
                g["name"], g["verts"], g["faces"], g["faceVertTotal"], len(g["uvs"])
            ))

        success, failed, unmatched = self._match_and_transfer(obj_groups, targets, use_api=True)

        cmds.select(orig_sel, replace=True)
        elapsed = time.time() - t0
        logger.info("v5.2 fast path completed in %.3fs" % elapsed)
        self._report(success, failed, unmatched, len(targets), elapsed)

    # ── 回退路径 ──
    def _do_get_fallback(self, targets, obj_p, t0, orig_sel):
        # 导入前快照
        before = set(cmds.ls(type="mesh", long=True) or [])
        logger.info("Before import: %d mesh shapes" % len(before))

        try:
            cmds.file(str(obj_p), i=True, type="OBJ", ignoreVersion=True, options="mo=1")
            logger.info("OBJ import completed.")
        except Exception as e:
            self._set_status(self.tr("import_fail") + " " + str(e), "error")
            logger.error("OBJ import error: %s" % e, exc_info=True)
            cmds.select(orig_sel, replace=True)
            return

        # 差集
        after = set(cmds.ls(type="mesh", long=True) or [])
        new_shapes = after - before
        logger.info("New mesh shapes: %d" % len(new_shapes))

        if not new_shapes:
            self._set_status(self.tr("no_geo"), "error")
            cmds.select(orig_sel, replace=True)
            return

        # 找 parent transform + 拓扑
        imp_meshes = []
        imp_transforms = []
        seen = set()
        for shape in new_shapes:
            if not cmds.objExists(shape):
                continue
            try:
                if cmds.getAttr(shape + ".intermediateObject"):
                    continue
            except Exception:
                pass
            parents = cmds.listRelatives(shape, p=True, f=True, type="transform") or []
            if not parents:
                continue
            parent = parents[0]
            if parent in seen:
                continue
            seen.add(parent)
            imp_transforms.append(parent)
            v, f = mesh_stats(shape)
            fvt = face_vert_total(shape)
            imp_meshes.append({
                "node": parent, "shape": shape, "name": short_name(parent),
                "verts": v, "faces": f, "faceVertTotal": fvt, "used": False,
            })

        if not imp_meshes:
            self._set_status(self.tr("no_geo"), "error")
            for t in imp_transforms:
                if cmds.objExists(t):
                    try:
                        cmds.delete(t)
                    except Exception:
                        pass
            cmds.select(orig_sel, replace=True)
            return

        logger.info("Imported meshes: %d" % len(imp_meshes))
        for i, imp in enumerate(imp_meshes):
            logger.info("  [%d] %s  v=%s  f=%s  fvt=%s" % (
                i, imp["name"], imp["verts"], imp["faces"], imp["faceVertTotal"]
            ))

        # 匹配 + API 复制（不是 polyTransfer）
        success, failed, unmatched = self._match_and_transfer_imported(imp_meshes, targets, imp_transforms)

        # 清理
        for t in imp_transforms:
            if cmds.objExists(t):
                try:
                    cmds.lockNode(t, lock=False)
                except Exception:
                    pass
        for t in imp_transforms:
            if cmds.objExists(t):
                try:
                    cmds.delete(t)
                except Exception:
                    pass

        cmds.select(orig_sel, replace=True)
        elapsed = time.time() - t0
        logger.info("v5.2 fallback completed in %.3fs" % elapsed)
        self._report(success, failed, unmatched, len(targets), elapsed)

    # ── 匹配 + API 写 UV（快速路径用）──
    def _match_and_transfer(self, obj_groups, targets, use_api=True):
        success = 0
        failed = 0

        # 建字典
        tgt_topo_count = {}
        tgt_by_topo = {}
        for j, tgt in enumerate(targets):
            key = (tgt["faceVertTotal"], tgt["faces"])
            tgt_topo_count[key] = tgt_topo_count.get(key, 0) + 1
            if key not in tgt_by_topo:
                tgt_by_topo[key] = []
            tgt_by_topo[key].append(j)

        obj_topo_count = {}
        for g in obj_groups:
            key = (g["faceVertTotal"], g["faces"])
            obj_topo_count[key] = obj_topo_count.get(key, 0) + 1

        obj_used = [False] * len(obj_groups)

        # L1: 唯一
        for gi, g in enumerate(obj_groups):
            key = (g["faceVertTotal"], g["faces"])
            if tgt_topo_count.get(key, 0) == 1 and obj_topo_count.get(key, 0) == 1:
                tgt_indices = tgt_by_topo.get(key, [])
                for j in tgt_indices:
                    if not targets[j]["used"]:
                        if self._api_write(g, targets[j]):
                            success += 1
                        else:
                            failed += 1
                        targets[j]["used"] = True
                        obj_used[gi] = True
                        break

        # L2: 同拓扑组
        rem_tgt = {}
        for tgt in targets:
            if tgt["used"]:
                continue
            key = (tgt["faceVertTotal"], tgt["faces"])
            rem_tgt[key] = rem_tgt.get(key, 0) + 1
        rem_obj = {}
        for gi, g in enumerate(obj_groups):
            if obj_used[gi]:
                continue
            key = (g["faceVertTotal"], g["faces"])
            rem_obj[key] = rem_obj.get(key, 0) + 1

        for topok in rem_tgt:
            if topok not in rem_obj:
                continue
            obj_idx = [gi for gi, g in enumerate(obj_groups)
                       if not obj_used[gi] and (g["faceVertTotal"], g["faces"]) == topok]
            tgt_idx = [j for j, tgt in enumerate(targets)
                       if not tgt["used"] and (tgt["faceVertTotal"], tgt["faces"]) == topok]
            n = min(len(obj_idx), len(tgt_idx))
            for k in range(n):
                if self._api_write(obj_groups[obj_idx[k]], targets[tgt_idx[k]]):
                    success += 1
                else:
                    failed += 1
                targets[tgt_idx[k]]["used"] = True
                obj_used[obj_idx[k]] = True

        # L3: 顺序兜底
        rem_obj_list = [g for gi, g in enumerate(obj_groups) if not obj_used[gi]]
        rem_tgt_list = [t for t in targets if not t["used"]]
        if rem_obj_list and rem_tgt_list and len(rem_obj_list) == len(rem_tgt_list):
            for k in range(len(rem_obj_list)):
                g = rem_obj_list[k]
                tgt = rem_tgt_list[k]
                if g["faces"] == tgt["faces"]:
                    if self._api_write(g, tgt):
                        success += 1
                    else:
                        failed += 1
                    tgt["used"] = True

        unmatched = [tgt["name"] for tgt in targets if not tgt["used"]]
        return success, failed, unmatched

    # ── 匹配 + API 复制 UV（回退路径用）──
    def _match_and_transfer_imported(self, imp_meshes, targets, imp_transforms):
        cmds.undoInfo(openChunk=True, chunkName="RizomBridgeFetch")
        success = 0
        failed = 0

        try:
            tgt_topo_count = {}
            tgt_by_topo = {}
            for j, tgt in enumerate(targets):
                key = (tgt["faceVertTotal"], tgt["faces"])
                tgt_topo_count[key] = tgt_topo_count.get(key, 0) + 1
                if key not in tgt_by_topo:
                    tgt_by_topo[key] = []
                tgt_by_topo[key].append(j)

            imp_topo_count = {}
            for imp in imp_meshes:
                key = (imp["faceVertTotal"], imp["faces"])
                imp_topo_count[key] = imp_topo_count.get(key, 0) + 1

            # L1
            for imp in imp_meshes:
                if imp["used"]:
                    continue
                key = (imp["faceVertTotal"], imp["faces"])
                if tgt_topo_count.get(key, 0) == 1 and imp_topo_count.get(key, 0) == 1:
                    tgt_indices = tgt_by_topo.get(key, [])
                    for j in tgt_indices:
                        if not targets[j]["used"]:
                            if self._api_copy(imp, targets[j]):
                                success += 1
                            else:
                                failed += 1
                            targets[j]["used"] = True
                            imp["used"] = True
                            break

            # L2
            rem_tgt = {}
            for tgt in targets:
                if tgt["used"]:
                    continue
                key = (tgt["faceVertTotal"], tgt["faces"])
                rem_tgt[key] = rem_tgt.get(key, 0) + 1
            rem_imp = {}
            for imp in imp_meshes:
                if imp["used"]:
                    continue
                key = (imp["faceVertTotal"], imp["faces"])
                rem_imp[key] = rem_imp.get(key, 0) + 1

            for topok in rem_tgt:
                if topok not in rem_imp:
                    continue
                imp_idx = [i for i, imp in enumerate(imp_meshes)
                           if not imp["used"] and (imp["faceVertTotal"], imp["faces"]) == topok]
                tgt_idx = [j for j, tgt in enumerate(targets)
                           if not tgt["used"] and (tgt["faceVertTotal"], tgt["faces"]) == topok]
                n = min(len(imp_idx), len(tgt_idx))
                for k in range(n):
                    imp = imp_meshes[imp_idx[k]]
                    tgt = targets[tgt_idx[k]]
                    if self._api_copy(imp, tgt):
                        success += 1
                    else:
                        failed += 1
                    tgt["used"] = True
                    imp["used"] = True

            # L3
            rem_imp_list = [imp for imp in imp_meshes if not imp["used"]]
            rem_tgt_list = [t for t in targets if not t["used"]]
            if rem_imp_list and rem_tgt_list and len(rem_imp_list) == len(rem_tgt_list):
                for k in range(len(rem_imp_list)):
                    imp = rem_imp_list[k]
                    tgt = rem_tgt_list[k]
                    if imp["faces"] == tgt["faces"]:
                        if self._api_copy(imp, tgt):
                            success += 1
                        else:
                            failed += 1
                        tgt["used"] = True

            unmatched = [tgt["name"] for tgt in targets if not tgt["used"]]
            return success, failed, unmatched

        except Exception as e:
            logger.error("Fallback transfer error: %s" % e, exc_info=True)
            cmds.undo()
            raise
        finally:
            cmds.undoInfo(closeChunk=True)

    # ── API 写入（快速路径）──
    def _api_write(self, obj_group, target_info):
        try:
            write_uvs_to_mesh(
                target_info["shape"],
                obj_group["uvs"],
                obj_group["uvPerFace"],
                obj_group["uvIds"],
            )
            logger.info("  OK: %s <-> %s" % (obj_group["name"], target_info["name"]))
            return True
        except Exception as e:
            logger.error("API write failed: %s -> %s: %s" % (
                obj_group["name"], target_info["name"], e
            ))
            return False

    # ── API 复制（回退路径）──
    def _api_copy(self, imp_info, target_info):
        try:
            copy_uvs_api(imp_info["shape"], target_info["shape"])
            logger.info("  OK: %s <-> %s" % (imp_info["name"], target_info["name"]))
            return True
        except Exception as e:
            logger.error("API copy failed: %s -> %s: %s" % (
                imp_info["name"], target_info["name"], e
            ))
            return False

    # ── 结果报告 ──
    def _report(self, success, failed, unmatched, total, elapsed):
        if unmatched:
            msg = self.tr("uv_partial").format(success, total, failed)
            msg += "  未匹配: " + ", ".join(unmatched[:5])
            if len(unmatched) > 5:
                msg += " ..."
            self._set_status(msg, "warning")
        elif success == total:
            self._set_status("%s/%s %s (%.1fs)" % (success, total, self.tr("uv_done"), elapsed), "info")
        elif success > 0:
            self._set_status(self.tr("uv_partial").format(success, total, failed), "warning")
        else:
            self._set_status(str(total) + self.tr("uv_fail").format(failed), "error")

    def closeEvent(self, event):
        self._alive = False
        self._kill_jobs()
        super(BridgePanel, self).closeEvent(event)


# ── 启动 ───────────────────────────────────────────
def _kill_orphan_jobs():
    try:
        for s in (cmds.scriptJob(listJobs=True) or []):
            try:
                parts = s.split(":")
                if not parts:
                    continue
                num = int(parts[0])
                if not cmds.scriptJob(exists=num):
                    continue
                p = cmds.scriptJob(query=True, parent=num)
                if p and "rizomUV" in str(p):
                    cmds.scriptJob(kill=num, force=True)
            except (ValueError, TypeError, Exception):
                pass
    except Exception:
        pass


def _place_in_workspace():
    global panel_instance
    if panel_instance is None:
        return
    try:
        ptr = omui.MQtUtil.findControl(WORKSPACE_CTRL)
        if not ptr:
            return
        wc = wrapInstance(int(ptr), QtWidgets.QWidget)
        layout = wc.layout()
        if layout is None:
            layout = QtWidgets.QVBoxLayout(wc)
            layout.setContentsMargins(0, 0, 0, 0)
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w and w.objectName() == "rizomUVBridgePanel":
                w.setParent(None)
                w.deleteLater()
        layout.addWidget(panel_instance)
    except Exception as e:
        cmds.warning("RizomBridge: Place failed: %s" % e)


def launch():
    global panel_instance, config
    title = "RizomUV <> Maya Bridge v5.2"

    _kill_orphan_jobs()

    if cmds.workspaceControl(WORKSPACE_CTRL, q=True, exists=True):
        try:
            cmds.deleteUI(WORKSPACE_CTRL, control=True)
        except Exception:
            pass

    if panel_instance is not None:
        try:
            panel_instance._kill_jobs()
            panel_instance.deleteLater()
        except Exception:
            pass
        finally:
            panel_instance = None

    if not config:
        cmds.warning("RizomBridge: Config manager failed.")
        return None

    try:
        panel_instance = BridgePanel()
    except Exception as e:
        cmds.warning("RizomBridge: Panel creation failed: %s" % e)
        return None

    try:
        cmds.workspaceControl(
            WORKSPACE_CTRL, label=title,
            retain=False, loadImmediately=True,
            initialWidth=300, minimumWidth=250,
        )
        _place_in_workspace()
        cmds.workspaceControl(WORKSPACE_CTRL, edit=True, visible=True)
    except Exception as e:
        cmds.warning("RizomBridge: Workspace control failed: %s" % e)

    return panel_instance


def run():
    r = launch()
    if r is not None:
        print("RizomUV Bridge v5.2 launched successfully.")
    return r


if __name__ == "__main__":
    run()
