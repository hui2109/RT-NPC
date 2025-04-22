import os
import shutil
import time
from collections import OrderedDict

import pydicom


def further_split_by_ct_tag(mixed_folder, output_root, tag_name="SeriesDescription"):
    """
    在已按 ID_Date 分类的 DICOM 文件夹内，根据 CT 图像的指定标签（如 SeriesDescription）进一步分类，
    并将对应的 RS/RP/RD 文件一并移动到新目录下（保持一套结构在一起）。

    参数：
        mixed_folder: 单个 ID_Date 文件夹路径。
        output_root: 输出根目录。
        tag_name: 用于进一步分类 CT 的标签名（如 SeriesDescription）。
    """
    base_name = os.path.basename(mixed_folder)
    # 初始化字典
    ct_dict = {}  # {SeriesInstanceUID: {"tag_str": ..., "files": [filepath1, filepath2, ...]}}
    rs_dict = {}  # {SOPInstanceUID: {"filepath": ..., "ref_series_uid": ...}}
    rp_dict = {}  # {SOPInstanceUID: {"filepath": ..., "ref_rs_uid": ...}}
    rd_dict = {}  # {filepath: (ref_rp_sop_uid, filename)}
    for filename in os.listdir(mixed_folder):
        if not filename.lower().endswith(".dcm"):
            continue
        filepath = os.path.join(mixed_folder, filename)
        try:
            ds = pydicom.dcmread(filepath, stop_before_pixels=True)
        except:
            continue
        if filename.startswith("CT"):
            series_uid = ds.SeriesInstanceUID
            tag_value = getattr(ds, tag_name, "Unknown")
            tag_str = str(tag_value).strip().replace(" ", "_").replace("/", "_")
            # 自定义区域
            # 这里用于对你提供的头文件进行定制化处理  例如对tag_str 文本分割
            tag_str = tag_str.split("-")[-1]

            if series_uid not in ct_dict:
                ct_dict[series_uid] = {"tag_str": tag_str, "files": []}
            ct_dict[series_uid]["files"].append((filepath, filename))

        elif filename.startswith("RS"):
            try:
                ref_uid = ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[0].RTReferencedSeriesSequence[0].SeriesInstanceUID
                rs_dict[ds.SOPInstanceUID] = {
                    "filepath": filepath,
                    "ref_series_uid": ref_uid,
                    "filename": filename
                }
            except:
                continue

        elif filename.startswith("RP"):
            try:
                ref_rs_uid = ds.ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID
                rp_dict[ds.SOPInstanceUID] = {
                    "filepath": filepath,
                    "ref_rs_uid": ref_rs_uid,
                    "filename": filename
                }
            except:
                continue

        elif filename.startswith("RD"):
            try:
                ref_rp_uid = ds.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID
                rd_dict[filepath] = (ref_rp_uid, filename)
            except:
                continue

    # 处理每组 CT
    for series_uid, ct_info in ct_dict.items():
        tag_str = ct_info["tag_str"]
        group_folder = os.path.join(output_root, f"{base_name}_{tag_str}")
        os.makedirs(group_folder, exist_ok=True)

        # 移动整套 CT 切片
        for filepath, filename in ct_info["files"]:
            shutil.move(filepath, os.path.join(group_folder, filename))

        # 找对应 RS
        for rs_uid, rs_info in rs_dict.items():
            if rs_info["ref_series_uid"] == series_uid:
                shutil.move(rs_info["filepath"], os.path.join(group_folder, rs_info["filename"]))

                # 找 RP
                for rp_uid, rp_info in rp_dict.items():
                    if rp_info["ref_rs_uid"] == rs_uid:
                        shutil.move(rp_info["filepath"], os.path.join(group_folder, rp_info["filename"]))

                        # 找 RD
                        for rd_path, (ref_rp_uid, rd_filename) in rd_dict.items():
                            if ref_rp_uid == rp_uid:
                                shutil.move(rd_path, os.path.join(group_folder, rd_filename))

    # 清空旧文件夹
    if not os.listdir(mixed_folder):
        os.rmdir(mixed_folder)
        print(f"🧹 清理空文件夹：{mixed_folder}")


def organize_rt_dcm_files(root_folder):
    # 遍历总文件夹下的所有患者ID文件夹
    for patient_id in os.listdir(root_folder):
        patient_path = os.path.join(root_folder, patient_id)

        if not os.path.isdir(patient_path):
            continue

        # 初始化数据结构
        ct_dict = {}  # {SeriesInstanceUID: (ct_file, date_str)}
        rs_dict = {}  # {RS_SOPInstanceUID: {'ct_series_uid': ..., 'files': [rs_files]}}
        rp_dict = {}  # {RP_SOPInstanceUID: {'file': rp_file, 'ref_rs_sop_uid': ...}}
        rd_dict = {}  # {rd_file: ref_rp_sop_uid}

        # 第一阶段：扫描并索引所有DICOM文件
        for filename in os.listdir(patient_path):
            filepath = os.path.join(patient_path, filename)
            print(f"开始处理患者 {filename} 的 DICOM 文件...")
            try:
                ds = pydicom.dcmread(filepath, stop_before_pixels=True)
            except Exception as e:
                print(f"无法读取文件 {filename}: {e}")
                continue

            # 处理CT文件
            if filename.startswith('CT'):
                series_uid = ds.SeriesInstanceUID
                try:
                    date_str = ds.AcquisitionDate
                except Exception as e:
                    date_str = ds.SeriesDate
                ID = ds.PatientID
                ct_dict[filename] = (filepath, date_str, ID, series_uid)

            # 处理RS文件
            elif filename.startswith('RS'):
                try:
                    rs_sop_uid = ds.SOPInstanceUID
                    # 获取关联的CT SeriesInstanceUID
                    ref_series_uid = \
                        ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[
                            0].RTReferencedSeriesSequence[
                            0].SeriesInstanceUID
                    rs_dict[filename] = (filepath, rs_sop_uid, ref_series_uid)
                except Exception as e:
                    print(f"RS文件 {filename} 索引失败: {e}")

            # 处理RP文件
            elif filename.startswith('RP'):
                try:
                    rp_sop_uid = ds.SOPInstanceUID
                    ref_rs_sop_uid = ds.ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID
                    rp_dict[filename] = (filepath, rp_sop_uid, ref_rs_sop_uid)
                except Exception as e:
                    print(f"RP文件 {filename} 索引失败: {e}")

            # 处理RD文件
            elif filename.startswith('RD'):
                try:
                    ref_rp_sop_uid = ds.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID
                    rd_dict[filename] = (filepath, ref_rp_sop_uid)
                except Exception as e:
                    print(f"RD文件 {filename} 索引失败: {e}")

        # 第二阶段：按CT系列整理文件
        file_path_all_dict = OrderedDict()
        for ct_filename in ct_dict:
            print('处理', ct_filename)
            ct_filepath, date_str, ID, series_uid = ct_dict[ct_filename]
            if not os.path.exists(os.path.join(os.path.dirname(patient_path), f'{ID}_{date_str}')):
                os.makedirs(os.path.join(os.path.dirname(patient_path), f'{ID}_{date_str}'))
                if os.path.exists(ct_filepath):
                    shutil.move(ct_filepath, os.path.join(os.path.dirname(patient_path), f'{ID}_{date_str}', ct_filename))
            else:
                if os.path.exists(ct_filepath):
                    shutil.move(ct_filepath, os.path.join(os.path.dirname(patient_path), f'{ID}_{date_str}', ct_filename))
                    for rs_filename in rs_dict:
                        print('   ', rs_filename)
                        rs_filepath, rs_sop_uid, rs_ref_uid = rs_dict[rs_filename]
                        if rs_ref_uid == series_uid:
                            if os.path.exists(rs_filepath):
                                shutil.move(rs_filepath, os.path.join(os.path.dirname(patient_path), f'{ID}_{date_str}', rs_filename))
                                for rp_filename in rp_dict:
                                    print('      ', rp_filename)
                                    rp_filepath, rp_sop_uid, rp_ref_uid = rp_dict[rp_filename]
                                    if rp_ref_uid == rs_sop_uid:
                                        if os.path.exists(rp_filepath):
                                            shutil.move(rp_filepath, os.path.join(os.path.dirname(patient_path), f'{ID}_{date_str}', rp_filename))
                                            for rd_filename in rd_dict:
                                                print('         ', rd_filename)
                                                rd_filepath, ref_rp_sop_uid = rd_dict[rd_filename]
                                                if ref_rp_sop_uid == rp_sop_uid:
                                                    if os.path.exists(rd_filepath):
                                                        shutil.move(rd_filepath, os.path.join(os.path.dirname(patient_path), f'{ID}_{date_str}', rd_filename))
        # 延迟1秒
        time.sleep(1)
        if not os.listdir(patient_path):
            os.rmdir(patient_path)


def main(root_folder):
    # 本代码是整理导出的文件夹A下每个ID文件夹内的所有dose plan  dcm 和rs文件 分好类并重命名文件夹
    organize_rt_dcm_files(root_folder)

    if_next_orgnize = 1  # 初步整理为ID date 后 是否进一步按照指定头文件信息整理 属于一套的RS RP RD不会拆散  如果要定制化分类 在函数中标注的 自定义区域中修改
    if if_next_orgnize == 1:
        for subfolder in os.listdir(root_folder):
            subfolder_path = os.path.join(root_folder, subfolder)
            further_split_by_ct_tag(subfolder_path, root_folder, tag_name="PatientName")


if __name__ == "__main__":
    root_folder = r"D:\exec_code\Python\RT-NPC\assets\images\original_images\NPCDATA"  # 修改为实际路径
    main(root_folder)
