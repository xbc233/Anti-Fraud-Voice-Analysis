import pandas as pd
from aip import AipSpeech
import time
import os
import random # 导入随机库，用于生成变化的语速和音调

# --- 配置 ---
# 【重要】在这里填入你在百度智能云上获取的凭证
APP_ID = '6972530'
API_KEY = 'tpmY23YZCEaHLHedC3akAa6x'
SECRET_KEY = 'zJnyxIca7PWC6RNw1sLEDVtziYTKEtze'

# 初始化AipSpeech对象
client = AipSpeech(APP_ID, API_KEY, SECRET_KEY)

# CSV 文件路径
csv_path = "验证码.csv"

# 音频输出目录
output_dir = "generated_audio_baidu_验证码" # 使用一个新的目录名
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# --- 【升级点1】扩充我们的音色库 ---
# 从你提供的列表中挑选一些有代表性的、听起来可能像诈骗电话或正常对话的音色
# 例如：标准男女声、情感男女声、专业主播、磁性男声、知性女声等
voices = [
    # 基础音库
    0,     # 度小美-标准女主播
    1,     # 度小宇-亲切男声
    3,     # 度逍遥-情感男声
    4,     # 度丫丫-童声 (可以模拟一些特定场景)
    # 精品音库
    106,   # 度博文-专业男主播 (适合冒充公检法)
    5,     # 度小娇-成熟女主播
    5118,  # 度小鹿-甜美女声
    # 臻品音库
    4176,  # 度有为-磁性男声
    4100,  # 度小雯-活力女主播
    4197,  # 度沁遥-知性女声
    4192,  # 度青川-温柔男声
    # 大模型音库 (效果最好，可以多加一些)
    4179,  # 度泽言-温暖男声
    4146,  # 度禧禧-阳光女声
    4189,  # 度涵竹-开朗女声 (多情感)
    4195   # 度怀安-磁性男声 (多情感)
]

# --- 主程序 ---
# 读取CSV文件，并只选择前300行
df_full = pd.read_csv(csv_path)
df = df_full.head(300)

print(f"成功读取CSV，将处理其中的前 {len(df)} 条数据。")

for index, row in df.iterrows():
    text_id = row['id']
    text_to_speak = row['text']
    label = row['label']
    
    # --- 【升级点2】随机化参数 ---
    # 随机选择一个发音人
    current_voice = random.choice(voices)
    
    # 随机生成语速和音调 (在合理的范围内)
    # 语速：4-7 (偏快、正常、偏慢)
    # 音调：4-6 (稍微变化，避免太夸张)
    random_speed = random.randint(4, 7)
    random_pitch = random.randint(4, 6)

    # 定义输出文件名，可以把更多信息加进去
    filename = f"{label}_{text_id}_voice{current_voice}_spd{random_speed}_pit{random_pitch}.mp3"
    audio_output_path = os.path.join(output_dir, filename)
    
    # 跳过已存在的文件
    filename = f"{label}_{text_id}_voice{current_voice}_spd{random_speed}_pit{random_pitch}.wav"
    audio_output_path = os.path.join(output_dir, filename)
    
    if os.path.exists(audio_output_path):
        print(f"文件 {filename} 已存在，跳过。")
        continue

    print(f"正在生成: {filename}")
    
    # 调用百度的语音合成API，并传入随机化的参数
    result = client.synthesis(text_to_speak, 'zh', 1, {
        'vol': 5,                # 音量，保持不变
        'per': current_voice,    # 使用随机选择的发音人
        'spd': random_speed,     # 使用随机生成的语速
        'pit': random_pitch,     # 使用随机生成的音调
        'aue': 6                 # 指定音频编码格式为 wav
    })

    # 如果result不是一个字典，说明发生错误
    if not isinstance(result, dict):
        with open(audio_output_path, 'wb') as f:
            f.write(result)
        print(f"语音已成功合成并保存到 {audio_output_path}")
    else:
        print(f"ID {text_id} 合成失败: {result}")

    # 避免请求过于频繁，稍微等待一下
    time.sleep(1)

print("所有语音生成完毕！")