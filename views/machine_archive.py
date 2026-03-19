import os
import re
import time
from datetime import datetime

import streamlit as st

from config import MACHINE_ARCHIVE_ABS_DIR
from core.navigation import go_home
from core.permissions import check_access
from crud.inventory import get_data
from views.components import render_archive_preview, render_file_manager, render_module_logs


def render_machine_archive():
    check_access('ARCHIVE')
    c_back, c_title = st.columns([2, 8])
    with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
    with c_title: st.header("📂 机台档案 ")

    st.info("💡 管理每台机器的电子档案（照片/文档），文件存储在物理文件夹中。")

    # 1. 查询区
    df_all = get_data()
    all_sns = df_all['流水号'].unique().tolist() if not df_all.empty else []

    # 支持输入或选择
    if 'archive_sn_search' not in st.session_state: st.session_state.archive_sn_search = ""

    col_search, col_info = st.columns([1, 2])
    with col_search:
        # 使用 selectbox 实现带搜索的选择
        selected_sn = st.selectbox("🔍 搜索/选择流水号", [""] + sorted(all_sns, reverse=True), key="archive_sn_select")

    if selected_sn:
        # 获取机台信息
        row = df_all[df_all['流水号'] == selected_sn].iloc[0]
        model = row['机型']
        status = row['状态']
        
        with col_info:
            st.markdown(f"### {selected_sn}")
            st.caption(f"机型: {model} | 状态: {status}")
            
        st.divider()
        
        # 准备物理路径
        sn_dir = os.path.join(MACHINE_ARCHIVE_ABS_DIR, selected_sn)
        if not os.path.exists(sn_dir):
            try: os.makedirs(sn_dir, exist_ok=True)
            except: pass
            
        # 2. 展示区 (照片墙)
        # 读取目录下所有图片
        image_files = []
        if os.path.exists(sn_dir):
            all_files = os.listdir(sn_dir)
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
            image_files = [f for f in all_files if os.path.splitext(f)[1].lower() in image_extensions]
            # 按时间倒序
            image_files.sort(key=lambda x: os.path.getmtime(os.path.join(sn_dir, x)), reverse=True)
            
        if image_files:
            st.markdown(f"#### 🖼️ 现有照片 ({len(image_files)} 张)")
            
            # 每行显示 4 张
            cols = st.columns(4)
            for idx, img_name in enumerate(image_files):
                img_path = os.path.join(sn_dir, img_name)
                with cols[idx % 4]:
                    st.image(img_path, caption=img_name, use_container_width=True)
                    # 删除按钮
                    if st.button("🗑️", key=f"del_img_{selected_sn}_{img_name}", help="删除此照片"):
                        try:
                            os.remove(img_path)
                            audit_log("Delete Archive Photo", f"Deleted {img_name} from {selected_sn}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"删除失败: {e}")
        else:
            st.info("暂无照片存档")
            
        st.divider()
        
        # 3. 上传区
        st.markdown("#### 📤 上传机台档案 (必填项)")
        st.info("💡 请输入对应部件编号，并上传照片。系统将自动使用编号重命名文件。")
        
        # 容器布局
        with st.container(border=True):
            # A. 关键部件 (Key Components)
            c_k1, c_k2, c_k3 = st.columns(3)
            
            with c_k1:
                val_wheel = st.text_input("🟢 手轮号 ", key=f"wheel_{selected_sn}")
                file_wheel = st.file_uploader("上传手轮照片", type=['jpg', 'png'], key=f"up_wheel_{selected_sn}")
            
            with c_k2:
                val_motor = st.text_input("🔵 电机号 ", key=f"motor_{selected_sn}")
                file_motor = st.file_uploader("上传电机照片", type=['jpg', 'png'], key=f"up_motor_{selected_sn}")
            
            with c_k3:
                val_board = st.text_input("🟠 板号 ", key=f"board_{selected_sn}")
                file_board = st.file_uploader("上传主板照片", type=['jpg', 'png'], key=f"up_board_{selected_sn}")
        
        st.write("")
        with st.container(border=True):
            # B. 其他照片 (Others)
            st.markdown("##### ⚪ 其他/备注照片")
            c_o1, c_o2 = st.columns([1, 2])
            with c_o1:
                val_other = st.text_input("图片说明 (选填)", placeholder="例如：机身侧面、包装等", key=f"other_txt_{selected_sn}")
            with c_o2:
                files_other = st.file_uploader("上传其他照片 (支持多选)", type=['jpg', 'png'], accept_multiple_files=True, key=f"up_other_{selected_sn}")

        if st.button("💾 保存所有档案照片", type="primary"):
            # 检查必填项：如果上传了图片，则必须有对应的编号
            errors = []
            if file_wheel and not val_wheel.strip(): errors.append("请填写【手轮号】")
            if file_motor and not val_motor.strip(): errors.append("请填写【电机号】")
            if file_board and not val_board.strip(): errors.append("请填写【板号】")
            
            if errors:
                for e in errors: st.error(e)
            else:
                count = 0
                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                def save_arch_file(fileobj, prefix, label_val):
                    if not fileobj: return False
                    ext = os.path.splitext(fileobj.name)[1].lower()
                    if not ext: ext = ".jpg"
                    # Clean filename
                    safe_label = re.sub(r'[\\/*?:"<>|]', "", str(label_val)).strip()
                    if not safe_label: safe_label = "Unamed"
                    
                    # Naming: {Prefix}_{Label}_{Timestamp}.jpg
                    # e.g. Wheel_WH123_20260226.jpg
                    final_name = f"{prefix}_{safe_label}_{ts_str}{ext}"
                    save_p = os.path.join(sn_dir, final_name)
                    
                    try:
                        with open(save_p, "wb") as f: f.write(fileobj.read())
                        return True
                    except: return False

                # 1. Save Wheel
                if save_arch_file(file_wheel, "手轮", val_wheel): count += 1
                # 2. Save Motor
                if save_arch_file(file_motor, "电机", val_motor): count += 1
                # 3. Save Board
                if save_arch_file(file_board, "板号", val_board): count += 1
                
                # 4. Save Others
                if files_other:
                    idx = 1
                    for f_obj in files_other:
                        p_fix = "其他"
                        if val_other.strip(): p_fix = val_other.strip()
                        # Avoid overwrite if multiple files
                        label_comb = f"{idx}"
                        if save_arch_file(f_obj, p_fix, label_comb): count += 1
                        idx += 1
                
                if count > 0:
                    audit_log("Upload Archive", f"Uploaded {count} photos for {selected_sn} (Wheel:{val_wheel}, Motor:{val_motor})")
                    st.success(f"成功归档 {count} 张照片！")
                    time.sleep(1); st.rerun()
                else:
                    st.warning("未检测到待保存的文件")

    # ---  销售下单 ---
