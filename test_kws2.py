import os
import struct
import wave
from datetime import datetime
import pvporcupine
import pvcobra


# --- 函数：处理单个WAV文件（此函数无需修改） ---
def process_wav_file(filepath, porcupine, cobra, keyword_names, vad_threshold):
    """
    使用Cobra VAD和Porcupine处理单个WAV文件。
    返回: (检测到的关键词名称 str 或 错误信息 或 None, 语音帧数 int, 总帧数 int)
    """
    try:
        with wave.open(filepath, 'rb') as wf:
            if wf.getnchannels() != 1: return "错误: 不是单声道", 0, 0
            if wf.getsampwidth() != 2: return "错误: 不是16-bit音频", 0, 0
            if wf.getframerate() != porcupine.sample_rate: return f"错误: 采样率不是 {porcupine.sample_rate}", 0, 0

            num_frames, frame_length = wf.getnframes(), porcupine.frame_length
            speech_frames_count, total_frames_count = 0, 0

            for i in range(0, num_frames, frame_length):
                frame = wf.readframes(frame_length)
                if len(frame) < frame_length * 2: break

                total_frames_count += 1
                pcm = struct.unpack_from("h" * frame_length, frame)

                if cobra.process(pcm) > vad_threshold:
                    speech_frames_count += 1
                    result = porcupine.process(pcm)
                    if result >= 0:
                        return keyword_names[result], speech_frames_count, total_frames_count

            return None, speech_frames_count, total_frames_count

    except Exception as e:
        return f"处理异常: {e}", 0, 0


# --- 主程序 ---
def main():
    # --- 参数设置 ---
    access_key = "wnNixNAHoeM9gS9YpmUqTuchNvkY64zXHxxMeQ3haqrU0fGPEsNvmQ=="
    keyword_paths = ["./验证码_zh_windows_v3_0_0.ppn"]
    keyword_names = ["验证码"]
    model_path = "./porcupine_params_zh.pv"
    wav_dirs = ["generated_audio_baidu_验证码"]
    vad_threshold = 0.2
    result_file = "detection_result_with_vad.txt"

    porcupine = None
    cobra = None

    # 【核心修改】使用一个大的 try...finally 结构包裹所有操作
    try:
        # --- 步骤1: 初始化引擎 ---
        porcupine = pvporcupine.create(
            access_key=access_key,
            keyword_paths=keyword_paths,
            model_path=model_path,
            sensitivities=[0.5] * len(keyword_paths)
        )
        cobra = pvcobra.create(access_key=access_key)
        print("✅ Porcupine 和 Cobra VAD 引擎初始化成功!")

        # --- 步骤2: 打开日志文件并处理所有音频 ---
        with open(result_file, 'w', encoding='utf-8') as out:
            out.write(f"# Porcupine & Cobra VAD 检测日志\n")
            out.write(f"# 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            out.write(f"# 监听关键词: {', '.join(keyword_names)}\n")
            out.write(f"# VAD 阈值: {vad_threshold}\n")

            total_files = 0
            correct_detections = 0

            for wav_dir in wav_dirs:
                if not os.path.isdir(wav_dir):
                    print(f"⚠️ 文件夹不存在: {wav_dir}")
                    continue

                expected_keyword = "验证码" if "验证码" in wav_dir else "转账"

                out.write(f"\n📁 正在扫描目录: {wav_dir} (预期关键词: '{expected_keyword}')\n{'=' * 50}\n")
                print(f"\n--- 正在处理目录: {wav_dir} (预期: '{expected_keyword}') ---")

                for filename in sorted(os.listdir(wav_dir)):
                    if not filename.lower().endswith(".wav"): continue

                    total_files += 1
                    filepath = os.path.join(wav_dir, filename)
                    print(f"🔍 正在分析文件: {filename}")

                    detected_result, speech_frames, total_frames = process_wav_file(
                        filepath, porcupine, cobra, keyword_names, vad_threshold
                    )

                    out.write(f"🎧 文件: {filename}\n")
                    out.write(f"   VAD 信息: {speech_frames} / {total_frames} 帧被判断为语音。\n")

                    if detected_result and not detected_result.startswith("错误"):
                        out.write(f"   检测结果: ✅ 命中 '{detected_result}'\n")
                        if detected_result == expected_keyword:
                            correct_detections += 1
                            out.write("   评判: ✔️ 正确\n")
                        else:
                            out.write(f"   评判: ❌ 错误 (预期为 '{expected_keyword}')\n")
                    elif detected_result and detected_result.startswith("错误"):
                        out.write(f"   检测结果: ❌ {detected_result}\n")
                    else:
                        out.write("   检测结果: ⭕️ 未命中关键词\n")

            # --- 步骤3: 在文件关闭前写入最终统计 ---
            accuracy = (correct_detections / total_files * 100) if total_files > 0 else 0
            summary = (
                f"\n\n📊 统计结果：\n"
                f"   总文件数: {total_files}\n"
                f"   正确检测数: {correct_detections}\n"
                f"   准确率: {accuracy:.2f}%\n"
            )
            print(summary)
            out.write(summary)

    # 你也可以在这里加 except 块来捕获特定异常
    except pvporcupine.PorcupineError as e:
        print(f"[严重错误] Porcupine 引擎发生致命错误: {e}")
    except Exception as e:
        print(f"[严重错误] 发生未知异常: {e}")

    # --- 步骤4: 最终清理资源 ---
    finally:
        if porcupine:
            porcupine.delete()
        if cobra:
            cobra.delete()
        print("\n✅ 程序结束，资源已释放。")


if __name__ == "__main__":
    main()