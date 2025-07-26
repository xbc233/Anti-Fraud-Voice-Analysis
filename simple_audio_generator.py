#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
阿里云语音合成音频生成器
基于 simple_audio_generator.py 的思路，使用阿里云 NLS 服务替代 ChatTTS
"""

import time
import threading
import re
import json
import os
from pathlib import Path
import datetime
import argparse
import cn2an
from typing import List, Dict, Optional

# 导入阿里云NLS SDK
import nls

# 阿里云NLS配置
URL = "wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1"
TOKEN = ""  # 参考https://help.aliyun.com/document_detail/450255.html获取token
APPKEY = ""  # 获取Appkey请前往控制台：https://nls-portal.console.aliyun.com/applist


def parse_slidev_md(md_file: str) -> List[Dict]:
    """解析Slidev markdown文件，提取slides和scripts"""
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 按照 --- 分割slides
    slides_raw = content.split('---')

    slides_data = []
    slide_id = 0

    for slide_raw in slides_raw:
        slide_raw = slide_raw.strip()
        if not slide_raw:
            continue

        slide_id += 1

        # 提取HTML注释中的script（语音合成文本）
        script_match = re.search(r'<!--\s*(.*?)\s*-->', slide_raw, re.DOTALL)
        script = ""
        duration = 120  # 默认120秒

        if script_match:
            comment_content = script_match.group(1)

            # 提取预计时长
            duration_match = re.search(r'预计时长[：:]\s*(\d+)秒', comment_content)
            if duration_match:
                duration = int(duration_match.group(1))

            # 清理script文本，去掉时长信息
            script = re.sub(r'预计时长[：:]\s*\d+秒', '', comment_content).strip()

        # 提取slide标题
        title_match = re.search(r'^#\s+(.+)$', slide_raw, re.MULTILINE)
        title = title_match.group(1) if title_match else f"Slide {slide_id}"

        if script:  # 只处理有script的slides
            slides_data.append({
                "id": slide_id,
                "title": title,
                "content": slide_raw,
                "script": script,
                "duration": duration
            })

    return slides_data


def normalize_numbers_in_text(text: str) -> str:
    """使用cn2an智能转换数字为中文读音"""
    # 使用正则表达式查找所有数字（包括整数和小数）
    numbers = re.findall(r'\d+\.\d+|\d+', text)

    # 对找到的数字进行排序，从长到短，防止替换时出错
    numbers.sort(key=len, reverse=True)

    for num_str in numbers:
        try:
            # 将字符串形式的数字转换为中文
            chinese_num = cn2an.an2cn(num_str, "low")
            # 在原始文本中进行替换
            text = text.replace(num_str, chinese_num, 1)
        except Exception as e:
            print(f"   ⚠️  数字转换失败: {num_str} -> {e}")
            continue

    return text


def preprocess_text(text: str) -> str:
    """预处理文本，优化语音合成效果"""
    # 1. 使用cn2an智能处理数字
    processed_text = normalize_numbers_in_text(text)

    # 2. 处理标点符号，添加适当的停顿
    processed_text = processed_text.replace('—', '，')  # 破折号 -> 逗号
    processed_text = processed_text.replace('：', '，')  # 冒号 -> 逗号
    processed_text = processed_text.replace('；', '，')  # 分号 -> 逗号
    processed_text = processed_text.replace('\n', '，')  # 换行 -> 逗号
    processed_text = processed_text.replace('  ', ' ')  # 多个空格 -> 单个空格

    # 3. 确保句子末尾有合适的结尾
    if processed_text and not processed_text.strip().endswith(('。', '.', '，')):
        processed_text += '。'

    return processed_text.strip()


class AliyunTtsGenerator:
    """阿里云TTS生成器类"""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.results = {}

    def on_metainfo(self, message, slide_id, *args):
        print(f"第{slide_id}页 - 元信息: {message}")

    def on_error(self, message, slide_id, *args):
        print(f"第{slide_id}页 - 错误: {args}")
        with self.lock:
            self.results[slide_id] = {"status": "error", "message": str(args)}

    def on_close(self, slide_id, file_handle, *args):
        print(f"第{slide_id}页 - 连接关闭")
        try:
            if file_handle:
                file_handle.close()
        except Exception as e:
            print(f"第{slide_id}页 - 关闭文件失败: {e}")

    def on_data(self, data, slide_id, file_handle, *args):
        try:
            if file_handle:
                file_handle.write(data)
        except Exception as e:
            print(f"第{slide_id}页 - 写入数据失败: {e}")

    def on_completed(self, message, slide_id, file_handle, output_path, *args):
        print(f"第{slide_id}页 - 生成完成: {message}")

        try:
            if file_handle:
                file_handle.close()

            # 计算文件大小和估计时长
            file_size = os.path.getsize(output_path)
            # WAV文件时长估算（采样率16000，16位，单声道）
            estimated_duration = file_size / (16000 * 2)  # 字节数 / (采样率 * 2字节)

            with self.lock:
                self.results[slide_id] = {
                    "status": "success",
                    "path": str(output_path),
                    "duration": estimated_duration,
                    "file_size": file_size
                }

        except Exception as e:
            print(f"第{slide_id}页 - 处理完成信息失败: {e}")
            with self.lock:
                self.results[slide_id] = {"status": "error", "message": str(e)}

    def generate_single_audio(self, slide: Dict, voice: str = "ailun") -> Optional[Dict]:
        """生成单个音频文件"""
        slide_id = slide['id']
        text = slide['script']
        title = slide['title']

        print(f"   开始生成第{slide_id}页音频: {title[:30]}...")

        # 预处理文本
        processed_text = preprocess_text(text)
        print(f"   原始文本长度: {len(text)} 字符")
        print(f"   处理后文本: {processed_text[:100]}...")

        # 设置输出文件路径
        output_path = self.output_dir / f"slide_{slide_id:02d}.wav"

        try:
            # 打开文件句柄
            file_handle = open(output_path, "wb")

            # 使用线程处理TTS
            def tts_thread():
                try:
                    tts = nls.NlsSpeechSynthesizer(
                        url=URL,
                        token=TOKEN,
                        appkey=APPKEY,
                        on_metainfo=lambda msg, *args: self.on_metainfo(msg, slide_id, *args),
                        on_data=lambda data, *args: self.on_data(data, slide_id, file_handle, *args),
                        on_completed=lambda msg, *args: self.on_completed(msg, slide_id, file_handle, output_path,
                                                                          *args),
                        on_error=lambda msg, *args: self.on_error(msg, slide_id, *args),
                        on_close=lambda *args: self.on_close(slide_id, file_handle, *args),
                        callback_args=[slide_id]
                    )

                    # 开始语音合成
                    result = tts.start(processed_text, voice=voice, aformat="wav")
                    print(f"   第{slide_id}页 - TTS启动结果: {result}")
                    return result
                except Exception as e:
                    print(f"   第{slide_id}页 - TTS线程异常: {e}")
                    # 设置错误状态，让主线程能够感知到异常
                    with self.lock:
                        self.results[slide_id] = {"status": "error", "message": f"TTS异常: {str(e)}"}
                    return None

            # 创建并启动线程
            thread = threading.Thread(target=tts_thread)
            thread.start()

            # 等待生成完成（最多等待60秒）
            max_wait_time = 60
            wait_time = 0
            while wait_time < max_wait_time:
                time.sleep(1)
                wait_time += 1

                with self.lock:
                    if slide_id in self.results:
                        result_info = self.results[slide_id]
                        if result_info["status"] == "success":
                            print(f"   ✅ 第{slide_id}页生成成功: {output_path}")
                            print(f"      时长: {result_info['duration']:.1f}秒")
                            print(f"      文件大小: {result_info['file_size'] / 1024:.1f}KB")

                            # 等待线程结束
                            thread.join(timeout=5)

                            return {
                                'slide_id': slide_id,
                                'audio_path': result_info['path'],
                                'duration': result_info['duration'],
                                'title': title,
                                'file_size': result_info['file_size']
                            }
                        elif result_info["status"] == "error":
                            print(f"   ❌ 第{slide_id}页生成失败: {result_info.get('message', '未知错误')}")
                            thread.join(timeout=5)
                            return None

            print(f"   ⏰ 第{slide_id}页生成超时")
            thread.join(timeout=5)
            return None

        except Exception as e:
            print(f"   ❌ 第{slide_id}页生成异常: {e}")
            return None
        finally:
            # 确保文件句柄关闭
            try:
                if 'file_handle' in locals() and file_handle:
                    file_handle.close()
            except:
                pass


def generate_audio_files(slides_data: List[Dict], output_dir: str, voice: str = "ailun") -> List[Dict]:
    """使用阿里云NLS生成音频文件"""
    print("🎵 开始使用阿里云NLS生成音频...")
    print(f"   语音: {voice}")
    print(f"   输出目录: {output_dir}")

    # 创建带时间戳的输出目录
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if Path(output_dir).exists():
        # 重命名旧目录作为备份
        backup_dir = f"{output_dir}_backup_{timestamp}"
        print(f"📦 备份旧目录: {output_dir} -> {backup_dir}")
        Path(output_dir).rename(backup_dir)

    # 创建新目录
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    print(f"📁 创建新的输出目录: {output_dir}")

    # 创建生成器实例
    generator = AliyunTtsGenerator(output_dir)

    audio_files = []
    total_slides = len(slides_data)

    for i, slide in enumerate(slides_data, 1):
        print(f"\n📢 进度: {i}/{total_slides}")

        audio_info = generator.generate_single_audio(slide, voice)
        if audio_info:
            audio_files.append(audio_info)

        # 添加延迟避免请求过于频繁
        if i < total_slides:
            time.sleep(2)

    print(f"\n🎉 音频生成完成！音频文件保存在: {output_dir.absolute()}")

    # 统计信息
    if audio_files:
        print(f"\n📊 生成统计:")
        total_duration = sum(audio['duration'] for audio in audio_files)
        total_size = sum(audio['file_size'] for audio in audio_files)

        print(f"   成功生成: {len(audio_files)}/{total_slides} 个音频文件")
        print(f"   总时长: {total_duration:.1f} 秒 ({total_duration / 60:.1f} 分钟)")
        print(f"   平均时长: {total_duration / len(audio_files):.1f} 秒")
        print(f"   总大小: {total_size / 1024 / 1024:.1f} MB")

        print("\n💡 后续步骤:")
        print("   1. 播放音频文件检查效果")
        print("   2. 如果满意，可以继续生成视频")
        print("   3. 如果不满意，可以调整语音参数重新生成")
    else:
        print("\n❌ 没有成功生成任何音频文件")

    return audio_files


def save_audio_info(audio_files: List[Dict], output_file: str):
    """保存音频信息到JSON文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(audio_files, f, ensure_ascii=False, indent=2)
    print(f"📄 音频信息已保存到: {output_file}")


def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='阿里云语音合成音频生成器 - 从Slidev文件生成音频')
    parser.add_argument('slidev_file',
                        help='Slidev markdown文件路径',

                        default='deepseek_markdown_20250721_3e7232.md',

                        nargs='?')
    parser.add_argument('-o', '--output-dir',
                        dest='audio_output_dir',
                        default='aliyun_audio_output1',
                        help='音频输出目录 (默认: aliyun_audio_output1)')
    parser.add_argument('--info-file',
                        dest='audio_info_file',
                        default='aliyun_audio_info.json',
                        help='音频信息JSON输出文件路径 (默认: aliyun_audio_info.json)')
    parser.add_argument('--voice',
                        dest='voice',
                        default='ailun',
                        help='语音音色 (默认: ailun，可选: aiqi, aijia, aixia等)')
    parser.add_argument('--debug',
                        action='store_true',
                        help='启用NLS调试信息（会产生大量日志）')

    args = parser.parse_args()

    # 根据参数决定是否启用NLS调试信息
    if args.debug:
        print("🐛 启用NLS调试信息...")
        nls.enableTrace(True)
    else:
        nls.enableTrace(False)

    print("🎵 阿里云语音合成音频生成器")
    print("=" * 60)

    # 使用命令行参数
    slidev_file = args.slidev_file
    audio_output_dir = args.audio_output_dir
    audio_info_file = args.audio_info_file
    voice = args.voice

    print(f"📝 输入文件: {slidev_file}")
    print(f"📁 输出目录: {audio_output_dir}")
    print(f"📄 信息文件: {audio_info_file}")
    print(f"🎭 语音音色: {voice}")
    if args.debug:
        print(f"🐛 调试模式: 开启")
    print("-" * 60)

    # 检查输入文件
    if not os.path.exists(slidev_file):
        print(f"❌ 找不到文件: {slidev_file}")
        return

    # 步骤1: 解析Slidev文件
    print("📖 解析Slidev文件...")
    slides_data = parse_slidev_md(slidev_file)
    print(f"✅ 找到 {len(slides_data)} 个包含脚本的slides")

    # 显示找到的脚本
    for slide in slides_data:
        print(f"   第{slide['id']}页: {slide['title']} (预计{slide['duration']}秒)")
        print(f"      脚本: {slide['script'][:50]}...")

    print("\n" + "=" * 60)

    # 步骤2: 生成音频
    audio_files = generate_audio_files(slides_data, audio_output_dir, voice)

    if audio_files:
        # 保存音频信息
        save_audio_info(audio_files, audio_info_file)

        print(f"\n✅ 音频生成完成！接下来可以:")
        print(f"   1. 播放 {audio_output_dir}/ 目录下的音频文件")
        print(f"   2. 运行Slidev导出图片")
        print(f"   3. 用FFmpeg合成视频")
    else:
        print("\n❌ 音频生成失败")


if __name__ == "__main__":
    main()
