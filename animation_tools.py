"""
Animation Tools - UV/节点动画工具

通过 Blender Driver 系统实现节点动画，无需写 Python 脚本。
支持 UV 滚动、旋转、缩放动画，以及节点输入值的关键帧动画。
"""

import bpy
import math
from typing import Optional
from .shader_tools import _result, _get_material, _get_node


def anim_add_uv_scroll(material_name: str, node_name: str,
                       speed_x: float = 0.0, speed_y: float = 0.0, speed_z: float = 0.0) -> dict:
    """为 Mapping 节点的 Location 添加基于帧的 Driver，实现 UV 滚动动画"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)

        if node.type != 'MAPPING':
            return _result(False, None, f"{node_name} 不是 Mapping 节点")

        speeds = [speed_x, speed_y, speed_z]
        axes = ['X', 'Y', 'Z']
        added = []

        for i, (speed, axis) in enumerate(zip(speeds, axes)):
            if speed == 0.0:
                continue

            loc_input = node.inputs.get('Location')
            if loc_input is None:
                return _result(False, None, "Mapping 节点没有 Location 输入")

            fcurve = loc_input.driver_add("default_value", i)
            driver = fcurve.driver
            driver.type = 'SCRIPTED'
            driver.expression = f"frame * {speed}"

            added.append(f"{axis}={speed}/帧")

        if not added:
            return _result(False, None, "至少需要一个轴的速度不为0")

        tips = (
            f"已为 {node_name} 添加UV滚动: {', '.join(added)}\n\n"
            "调整提示:\n"
            f"- 在节点编辑器中选择 {node_name}，Location 输入会显示紫色(有Driver)\n"
            "- 修改速度: 在 Driver 编辑器中修改 expression 的系数\n"
            "- 删除动画: 使用 anim_remove_driver 工具"
        )
        return _result(True, tips)

    except Exception as e:
        return _result(False, None, str(e))


def anim_add_uv_rotate(material_name: str, node_name: str,
                       speed: float = 0.01, axis: str = "Z") -> dict:
    """为 Mapping 节点的 Rotation 添加 Driver，实现 UV 旋转动画"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)

        if node.type != 'MAPPING':
            return _result(False, None, f"{node_name} 不是 Mapping 节点")

        axis_map = {'X': 0, 'Y': 1, 'Z': 2}
        axis = axis.upper()
        if axis not in axis_map:
            return _result(False, None, f"无效轴: {axis}，可用: X, Y, Z")

        rot_input = node.inputs.get('Rotation')
        if rot_input is None:
            return _result(False, None, "Mapping 节点没有 Rotation 输入")

        idx = axis_map[axis]
        fcurve = rot_input.driver_add("default_value", idx)
        driver = fcurve.driver
        driver.type = 'SCRIPTED'
        driver.expression = f"frame * {speed}"

        tips = (
            f"已为 {node_name} 添加UV旋转: {axis}轴, 速度={speed}弧度/帧\n\n"
            "调整提示:\n"
            f"- 当前速度 {speed} 弧度/帧 ≈ {round(math.degrees(speed), 2)} 度/帧\n"
            "- 加快: 增大 speed 值\n"
            "- 反转: 使用负数 speed"
        )
        return _result(True, tips)

    except Exception as e:
        return _result(False, None, str(e))


def anim_add_uv_scale(material_name: str, node_name: str,
                      speed_x: float = 0.0, speed_y: float = 0.0, speed_z: float = 0.0,
                      base_scale: float = 1.0) -> dict:
    """为 Mapping 节点的 Scale 添加 Driver，实现 UV 缩放动画"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)

        if node.type != 'MAPPING':
            return _result(False, None, f"{node_name} 不是 Mapping 节点")

        speeds = [speed_x, speed_y, speed_z]
        axes = ['X', 'Y', 'Z']
        added = []

        for i, (speed, axis) in enumerate(zip(speeds, axes)):
            if speed == 0.0:
                continue

            scale_input = node.inputs.get('Scale')
            if scale_input is None:
                return _result(False, None, "Mapping 节点没有 Scale 输入")

            fcurve = scale_input.driver_add("default_value", i)
            driver = fcurve.driver
            driver.type = 'SCRIPTED'
            driver.expression = f"{base_scale} + frame * {speed}"

            added.append(f"{axis}={speed}/帧(基础={base_scale})")

        if not added:
            return _result(False, None, "至少需要一个轴的速度不为0")

        tips = (
            f"已为 {node_name} 添加UV缩放动画: {', '.join(added)}\n\n"
            "调整提示:\n"
            "- base_scale 是初始缩放值\n"
            "- speed 控制每帧缩放变化量\n"
            "- 用 sin(frame*0.1) 可做呼吸/脉动效果"
        )
        return _result(True, tips)

    except Exception as e:
        return _result(False, None, str(e))


def anim_add_value_driver(material_name: str, node_name: str,
                          input_name: str, expression: str,
                          index: int = -1) -> dict:
    """为任意节点输入添加 Driver 表达式动画

    expression 中可用变量: frame (当前帧)
    常用表达式:
      "frame * 0.01"          - 线性增长
      "sin(frame * 0.1)"      - 正弦波动
      "0.5 + 0.5*sin(frame*0.05)" - 0~1范围波动
      "(frame % 60) / 60"     - 60帧循环
    """
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)

        inp = node.inputs.get(input_name)
        if inp is None:
            return _result(False, None, f"输入不存在: {input_name}")

        if index >= 0:
            fcurve = inp.driver_add("default_value", index)
        else:
            fcurve = inp.driver_add("default_value")

        driver = fcurve.driver
        driver.type = 'SCRIPTED'
        driver.expression = expression

        tips = (
            f"已为 {node_name}.{input_name} 添加Driver: {expression}\n\n"
            "调整提示:\n"
            "- 在Driver编辑器中可修改表达式\n"
            "- 可用函数: sin, cos, tan, abs, min, max, pow, sqrt\n"
            "- 可用变量: frame (当前帧号)"
        )
        return _result(True, tips)

    except Exception as e:
        return _result(False, None, str(e))


def anim_add_keyframe(material_name: str, node_name: str,
                      input_name: str, frame: int, value,
                      index: int = -1) -> dict:
    """为节点输入在指定帧插入关键帧"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)

        inp = node.inputs.get(input_name)
        if inp is None:
            return _result(False, None, f"输入不存在: {input_name}")

        if isinstance(value, (list, tuple)):
            for i, v in enumerate(value):
                inp.default_value[i] = v
            inp.keyframe_insert("default_value", frame=frame)
        else:
            if index >= 0:
                inp.default_value[index] = value
                inp.keyframe_insert("default_value", index=index, frame=frame)
            else:
                inp.default_value = value
                inp.keyframe_insert("default_value", frame=frame)

        return _result(True, f"已在第 {frame} 帧为 {node_name}.{input_name} 插入关键帧: {value}")

    except Exception as e:
        return _result(False, None, str(e))


def anim_remove_driver(material_name: str, node_name: str,
                       input_name: str, index: int = -1) -> dict:
    """移除节点输入上的 Driver"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)

        inp = node.inputs.get(input_name)
        if inp is None:
            return _result(False, None, f"输入不存在: {input_name}")

        if index >= 0:
            inp.driver_remove("default_value", index)
        else:
            inp.driver_remove("default_value")

        return _result(True, f"已移除 {node_name}.{input_name} 的Driver")

    except Exception as e:
        return _result(False, None, str(e))


def execute_anim_tool(tool_name: str, arguments: dict) -> dict:
    try:
        tools_map = {
            "anim_add_uv_scroll": anim_add_uv_scroll,
            "anim_add_uv_rotate": anim_add_uv_rotate,
            "anim_add_uv_scale": anim_add_uv_scale,
            "anim_add_value_driver": anim_add_value_driver,
            "anim_add_keyframe": anim_add_keyframe,
            "anim_remove_driver": anim_remove_driver,
        }
        func = tools_map.get(tool_name)
        if func:
            return func(**arguments)
        return _result(False, None, f"未知动画工具: {tool_name}")
    except Exception as e:
        return _result(False, None, str(e))
