#!/bin/bash

# 反诈骗语音系统一键安装脚本（使用内置测试API Key）

echo "正在安装反诈骗语音分析系统..."

# 安装系统依赖
sudo apt-get update
sudo apt-get install -y python3-pip ffmpeg

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装Python依赖
echo "正在安装Python依赖..."
pip install torch torchaudio torchvision
pip install openai-whisper pandas pvporcupine pvcobra cn2an python-dotenv
pip install aliyun-python-sdk-core aliyun-python-sdk-nls-cloud-meta nls-python-sdk
pip install chardet
pip install baidu-aip

# 创建必要的目录
mkdir -p call_cases2 generated_audio_baidu_验证码 aliyun_audio_output1

echo "安装完成！"
echo "您可以直接运行以下命令测试系统："
echo "1. 生成测试音频: python generated_audio.py"
echo "2. 运行关键词检测: python test_kws2.py"
echo "3. 运行深度分析: python deepseek_analyzer.py"