import os
import time
import base64

import pandas as pd
import streamlit as st

from config import BASE_DIR, MACHINE_ARCHIVE_ABS_DIR, MAMMOTH_AVAILABLE, mammoth
from core.file_manager import delete_contract_file, save_contract_file
from crud.contracts import get_contract_files
from crud.logs import get_transaction_logs

def render_archive_preview(sn):
    """Render archive photos for a machine SN in an interactive grid."""
    if not sn: return
    archive_path = os.path.join(MACHINE_ARCHIVE_ABS_DIR, sn)
    if not os.path.exists(archive_path):
        st.info(f"🚫 该机台 ({sn}) 暂无照片存档")
        return
    
    # Get images
    try:
        all_files = os.listdir(archive_path)
    except Exception:
        st.error(f"无法读取目录: {archive_path}")
        return
        
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
    images = [f for f in all_files if os.path.splitext(f)[1].lower() in image_extensions]
    # Sort by mtime desc
    images.sort(key=lambda x: os.path.getmtime(os.path.join(archive_path, x)), reverse=True)
    
    count = len(images)
    st.markdown(f"**📸 照片总数: {count} 张**")
    
    if count == 0:
        st.warning("该机台目录下无图片文件")
        return

    # Pagination Logic
    BATCH_SIZE = 8
    show_all_key = f"show_all_photos_{sn}"
    
    # Display toggle for show all
    is_show_all = st.checkbox("显示全部照片", key=show_all_key)
    
    display_images = images if is_show_all else images[:BATCH_SIZE]
    
    cols = st.columns(4)
    for idx, img_name in enumerate(display_images):
        img_path = os.path.join(archive_path, img_name)
        with cols[idx % 4]:
            try:
                st.image(img_path, caption=img_name, use_container_width=True)
            except Exception:
                st.error("加载失败")
    
    if count > BATCH_SIZE and not is_show_all:
        st.caption(f"还有 {count - BATCH_SIZE} 张照片未显示，勾选上方选框查看全部。")



def render_module_logs(filter_keywords):
    df_log = get_transaction_logs(limit=500)
    if df_log.empty:
        return
    if filter_keywords:
        mask = df_log['操作类型'].apply(lambda x: any(k in str(x) for k in filter_keywords))
        df_show = df_log[mask]
    else:
        df_show = df_log
    if not df_show.empty:
        with st.expander("📜 近期操作日志 (Recent Logs)", expanded=False):
            st.dataframe(df_show, use_container_width=True, hide_index=True)


def render_file_manager(contract_id, customer_name, default_expanded=True, key_suffix=""):
    """
    渲染合同文件管理组件
    :param contract_id: 合同号
    :param customer_name: 客户名 (用于上传)
    :param default_expanded: 是否默认展开
    :param key_suffix: 避免 key 冲突的后缀
    """
    
    # 容器或折叠面板
    container = st.container()
    if not default_expanded:
        container = st.expander("📎 合同附件 (点击展开)", expanded=False)
    
    with container:
        c_files = get_contract_files(contract_id)
        if default_expanded: 
            st.divider()
            st.markdown("#### 📎 合同附件管理")
        
        if not c_files.empty:
            # Default preview: auto-select the first file if none selected
            preview_key = f"preview_target_{contract_id}{key_suffix}"
            if preview_key not in st.session_state:
                st.session_state[preview_key] = c_files.iloc[0]['file_name']

            # File List View
            for _, f_row in c_files.iterrows():
                f_name = f_row['file_name']
                f_path = f_row['file_path']
                abs_path = os.path.join(BASE_DIR, f_path)
                
                # --- Path Recovery Logic for Legacy/Moved Files ---
                if not os.path.exists(abs_path):
                    # Try removing 'contracts/' prefix if present (Migration scenario)
                    if "contracts" in f_path:
                        alt_path = f_path.replace("contracts/", "").replace("contracts\\", "")
                        alt_abs_path = os.path.join(BASE_DIR, alt_path)
                        if os.path.exists(alt_abs_path):
                            f_path = alt_path
                            abs_path = alt_abs_path
                # ---------------------------------------------------

                col_icon, col_name, col_info, col_act = st.columns([0.5, 3, 2, 2.5])
                
                with col_icon:
                    ext = os.path.splitext(f_name)[1].lower()
                    icon = "📄"
                    if ext in ['.jpg', '.jpeg', '.png']: icon = "🖼️"
                    elif ext == '.pdf': icon = "📕"
                    elif ext in ['.doc', '.docx']: icon = "📝"
                    st.write(f"### {icon}")
                    
                with col_name:
                    st.write(f"**{f_name}**")
                
                with col_info:
                    st.caption(f"👤 {f_row['uploader']}\n🕒 {f_row['upload_time']}")
                    
                with col_act:
                    c_a1, c_a2, c_a3 = st.columns(3)
                    with c_a1:
                        # Download
                        if os.path.exists(abs_path):
                            with open(abs_path, "rb") as f:
                                st.download_button("下载", f.read(), file_name=f_name, key=f"dl_{f_row.name}{key_suffix}", help="下载")
                        else:
                            st.error("文件丢失")
                    with c_a2:
                        # Preview Toggle
                        if st.button("预览", key=f"prev_{f_row.name}{key_suffix}", help="预览"):
                            st.session_state[preview_key] = f_name
                            st.rerun()
                    with c_a3:
                        # Delete
                        if st.button("删除", key=f"del_{f_row.name}{key_suffix}", help="删除"):
                            ok, msg = delete_contract_file(contract_id, f_name)
                            if ok:
                                st.success(msg)
                                if st.session_state.get(preview_key) == f_name:
                                    del st.session_state[preview_key]
                                time.sleep(0.5); st.rerun()
                            else: st.error(msg)
            
            # Preview Area
            target_file_name = st.session_state.get(preview_key)
            if target_file_name:
                # Find the record
                target_rec = c_files[c_files['file_name'] == target_file_name]
                if not target_rec.empty:
                    f_path = target_rec.iloc[0]['file_path']
                    abs_path = os.path.join(BASE_DIR, f_path)
                    
                    # --- Path Recovery for Preview ---
                    if not os.path.exists(abs_path):
                         if "contracts" in f_path:
                             alt_path = f_path.replace("contracts/", "").replace("contracts\\", "")
                             alt_abs_path = os.path.join(BASE_DIR, alt_path)
                             if os.path.exists(alt_abs_path):
                                 abs_path = alt_abs_path
                    # ---------------------------------
                    
                    ext = os.path.splitext(target_file_name)[1].lower()
                    
                    st.info(f"正在预览: {target_file_name}")
                    if os.path.exists(abs_path):
                        if ext in ['.jpg', '.jpeg', '.png']:
                            st.image(abs_path, use_container_width=True)
                        elif ext == '.pdf':
                            import base64
                            with open(abs_path, "rb") as f:
                                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
                            st.markdown(pdf_display, unsafe_allow_html=True)
                        elif ext == '.docx':
                            if MAMMOTH_AVAILABLE:
                                try:
                                    with open(abs_path, "rb") as docx_file:
                                        result = mammoth.convert_to_html(docx_file)
                                    html = (result.value or "").strip()
                                    if html:
                                        st.markdown(html, unsafe_allow_html=True)
                                        if result.messages:
                                            st.warning(f"文档已预览，但存在 {len(result.messages)} 条兼容性提示，部分格式可能与原文档不完全一致。")
                                    else:
                                        st.warning("docx 已加载，但未提取到可预览内容，请下载原文件查看。")
                                except Exception as e:
                                    import logging
                                    logging.error(f"docx 解析异常: {e}", exc_info=True)
                                    st.error(f"docx 预览解析失败，已记录日志。错误信息: {e}")
                                    with open(abs_path, "rb") as f:
                                        st.download_button("下载原文件", f.read(), file_name=target_file_name, key=f"dl_docx_fallback_{contract_id}{key_suffix}")
                            else:
                                import logging
                                logging.error("依赖缺失: mammoth 库未安装，无法进行 docx 预览。")
                                st.warning("系统缺少 mammoth 依赖库，无法在线预览 docx 文件。请联系管理员安装。")
                                with open(abs_path, "rb") as f:
                                    st.download_button("直接下载", f.read(), file_name=target_file_name, key=f"dl_docx_fallback_no_mammoth_{contract_id}{key_suffix}")
                        else:
                            st.info("此格式不支持在线预览，请下载查看")
                    else:
                        st.error("文件不存在")
        else:
            st.info("暂无附件")

        # Upload New
        with st.expander("📤 上传新附件 (支持覆盖)", expanded=False):
            new_files = st.file_uploader("拖拽文件到此处", accept_multiple_files=True, key=f"new_up_{contract_id}{key_suffix}", type=['pdf', 'doc', 'docx', 'jpg', 'jpeg'])
            overwrite = st.checkbox("遇到同名文件时自动覆盖", value=True, key=f"ov_{contract_id}{key_suffix}")
            
            # 检测 .doc 并显示转换选项
            convert_option = False
            has_doc = False
            if new_files:
                for nf in new_files:
                    if nf.name.lower().endswith('.doc'):
                        has_doc = True
                        break
            
            if has_doc:
                st.warning("⚠️ 检测到旧版 Word (.doc) 格式")
                convert_option = st.checkbox("🔄 自动转换为 .docx (推荐，方便在线预览)", value=True, key=f"cv_{contract_id}{key_suffix}", help="如果不勾选，将保留原始 .doc 格式，可能无法在线预览")

            if new_files and st.button("开始上传", key=f"btn_up_{contract_id}{key_suffix}"):
                cnt = 0
                for nf in new_files:
                    # Check exist
                    if not c_files.empty and nf.name in c_files['file_name'].values:
                        if overwrite:
                            delete_contract_file(contract_id, nf.name)
                        else:
                            st.warning(f"跳过同名文件: {nf.name}"); continue
                    
                    # Pass convert_option
                    ok, msg = save_contract_file(nf, customer_name, contract_id, st.session_state.operator_name, convert_to_docx=convert_option)
                    if ok: cnt += 1
                
                if cnt > 0:
                    st.success(f"成功上传 {cnt} 个文件！")
                    time.sleep(1); st.rerun()
