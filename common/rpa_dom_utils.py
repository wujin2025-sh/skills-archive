#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RPA DOM Utils - 统一 Playwright DOM 操作与自愈选择器辅助模块
包含：
1. 2D 空间物理距离节点定位（TreeWalker 算子）
2. React/Vue 原型链双向绑定赋值
3. 自愈式多 Selector 容错链（Self-healing Selectors）
4. 动态自适应延时缩放算法 (TimeWrapper)
"""

import time
import math
import sys
from typing import List, Optional, Union, Dict, Any

class TimeWrapper:
    """动态自适应延时缩放类，在确保 DOM 渲染稳定的前提下提升 30% 执行效率"""

    @staticmethod
    def sleep(seconds: float):
        if seconds >= 4.0:
            time.sleep(seconds * 0.6)   # 长页面跳转/重定向等待缩短 40%
        elif seconds >= 2.0:
            time.sleep(seconds * 0.75)  # 弹窗/下拉展开等待缩短 25%
        else:
            time.sleep(seconds * 0.85)  # 键盘输入/状态同步等待缩短 15%


async def safe_click(page_or_frame, selectors: List[str], timeout: int = 3000) -> bool:
    """
    自愈式选择器点击：按优先级依次尝试列表中的 Selector，只要有一个成功即返回 True。
    """
    for selector in selectors:
        try:
            elem = page_or_frame.locator(selector).first
            if await elem.is_visible(timeout=timeout):
                await elem.click()
                return True
        except Exception:
            continue
    return False


async def safe_fill(page_or_frame, selectors: List[str], value: str, timeout: int = 3000) -> bool:
    """
    自愈式选择器填值：按优先级尝试 Selector 列表进行输入。
    """
    for selector in selectors:
        try:
            elem = page_or_frame.locator(selector).first
            if await elem.is_visible(timeout=timeout):
                await elem.fill(value)
                return True
        except Exception:
            continue
    return False


async def force_input_value(page, selector: str, value: str, trigger_backspace: bool = True):
    """
    针对 React/Vue 双向绑定的受控 Input 组件，通过原型链 Setter 强制注入 value 并派发事件，
    可选模拟 Backspace + 重新敲击末尾字符强行唤醒 AutoComplete 下拉搜索。
    """
    js_script = """
    (args) => {
        const { selector, val } = args;
        const input = document.querySelector(selector);
        if (!input) return false;
        
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(input, val);
        
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
    }
    """
    success = await page.evaluate(js_script, {"selector": selector, "val": value})
    if success and trigger_backspace and len(value) > 0:
        # 物理模拟一次退格加重新输入，确保 Ant Design AutoComplete 等事件感知
        await page.focus(selector)
        await page.keyboard.press("Backspace")
        await page.keyboard.type(value[-1])
    return success


async def find_nearest_element_2d(
    page,
    anchor_text: str,
    target_selector: str,
    weight_y: float = 1.0,
    weight_x: float = 0.3
) -> Optional[Dict[str, Any]]:
    """
    利用 JavaScript TreeWalker 2D 空间物理距离算法：
    先定位锚点标题文本的屏幕坐标 (kwY, kwX)，扫描全页面所有匹配 target_selector 的目标元素，
    利用加权欧氏距离 Math.abs(btnY - kwY) * weight_y + Math.abs(btnX - kwX) * weight_x
    精准锁定并返回距离锚点最近的目标元素。
    """
    js_code = """
    (args) => {
        const { anchorText, targetSelector, weightY, weightX } = args;
        
        // 查找包含指定文本的锚点元素
        let anchorNode = null;
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        while (walker.nextNode()) {
            if (walker.currentNode.nodeValue.includes(anchorText)) {
                anchorNode = walker.currentNode.parentElement;
                break;
            }
        }
        
        if (!anchorNode) return null;
        const anchorRect = anchorNode.getBoundingClientRect();
        const kwY = anchorRect.top;
        const kwX = anchorRect.left;
        
        // 查找所有目标元素
        const targets = Array.from(document.querySelectorAll(targetSelector));
        let bestTarget = null;
        let minDistance = Infinity;
        
        targets.forEach((elem, index) => {
            const rect = elem.getBoundingClientRect();
            // 过滤未在页面上显示的元素
            if (rect.width === 0 && rect.height === 0) return;
            
            const dist = Math.abs(rect.top - kwY) * weightY + Math.abs(rect.left - kwX) * weightX;
            if (dist < minDistance) {
                minDistance = dist;
                bestTarget = { index: index, rect: { top: rect.top, left: rect.left } };
            }
        });
        
        return bestTarget;
    }
    """
    res = await page.evaluate(js_code, {
        "anchorText": anchor_text,
        "targetSelector": target_selector,
        "weightY": weight_y,
        "weightX": weight_x
    })
    return res
