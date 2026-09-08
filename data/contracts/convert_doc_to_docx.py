#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量将 .doc 文件转换为 .docx 文件
需要安装 pywin32: pip install pywin32
"""

import os
import sys
from pathlib import Path
import win32com.client as win32


def convert_doc_to_docx(doc_path, word=None, delete_original=False):
    """
    将单个 .doc 文件转换为 .docx

    Args:
        doc_path: .doc 文件的完整路径
        word: Word 应用程序对象（可选）
        delete_original: 是否删除原 .doc 文件

    Returns:
        转换后的 .docx 文件路径，失败返回 None
    """
    doc_path = Path(doc_path)
    docx_path = doc_path.with_suffix('.docx')

    # 如果 .docx 文件已存在，询问是否覆盖
    if docx_path.exists():
        if delete_original:
            print(f"跳过（.docx 已存在）: {doc_path.relative_to(doc_path.parents[-2])}")
            return None
        else:
            print(f"跳过（已存在）: {doc_path.relative_to(doc_path.parents[-2])}")
            return str(docx_path)

    try:
        # 如果未提供 word 对象，创建一个临时的
        close_word = False
        if word is None:
            word = win32.gencache.EnsureDispatch('Word.Application')
            word.Visible = False
            close_word = True

        # 打开 .doc 文件
        doc = word.Documents.Open(str(doc_path.absolute()))

        # 另存为 .docx (16 表示 wdFormatXMLDocument)
        doc.SaveAs2(str(docx_path.absolute()), FileFormat=16)

        # 关闭文档
        doc.Close()

        print(f"转换成功: {doc_path.relative_to(doc_path.parents[-2])}")

        # 删除原 .doc 文件
        if delete_original and docx_path.exists():
            doc_path.unlink()
            print(f"  已删除原文件: {doc_path.name}")

        # 如果是临时创建的 word 对象，关闭它
        if close_word:
            word.Quit()

        return str(docx_path)

    except Exception as e:
        print(f"转换失败: {doc_path.relative_to(doc_path.parents[-2])} - 错误: {e}")
        if close_word:
            word.Quit()
        return None


def main():
    # 获取当前脚本所在目录
    current_dir = Path(__file__).parent

    # 递归查找所有子文件夹中的 .doc 文件
    doc_files = list(current_dir.rglob('*.doc'))

    if not doc_files:
        print("未找到任何 .doc 文件")
        return

    print(f"找到 {len(doc_files)} 个 .doc 文件（包括子文件夹）")
    print("-" * 60)

    # 创建 Word 应用程序实例（复用以提高效率）
    word = win32.gencache.EnsureDispatch('Word.Application')
    word.Visible = False

    success_count = 0
    skip_count = 0
    fail_count = 0

    for doc_file in doc_files:
        result = convert_doc_to_docx(doc_file, word, delete_original=True)
        if result:
            success_count += 1
        elif doc_file.with_suffix('.docx').exists():
            skip_count += 1
        else:
            fail_count += 1

    # 关闭 Word 应用程序
    word.Quit()

    print("-" * 60)
    print(f"转换完成! 成功: {success_count}, 跳过: {skip_count}, 失败: {fail_count}, 总计: {len(doc_files)}")


if __name__ == '__main__':
    main()
