import torch
import whisper
import os
import time
import openai
import json

# --- 1. 初始化模型和客户端 ---
# (这部分代码保持不变，假设您已经填入了有效的API Key和配置)
device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")

print("Loading Speech-to-Text (Whisper) model...")
asr_model = whisper.load_model("base", device=device)
print("\n--- ASR model loaded successfully! ---\n")

# --- 初始化 LLM 客户端 (以DeepSeek为例，也可换成OpenAI) ---
try:
    # 替换成你的API Key
    api_key = "sk-ae92957e3964439e9b2fac3660d8ddff"
    if not api_key:
        raise ValueError("API_KEY environment variable not found.")

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1" # 如果用ChatGPT，请注释或删除此行
    )
    client.models.list() # 测试连接
    print("--- LLM client initialized successfully! ---\n")
    
except Exception as e:
    print(f"--- [ERROR] Failed to initialize LLM client: {e} ---")
    client = None


# --- 2. 定义分析函数 ---

PROMPT = "这是一段可能包含金融、转账、汇款、验证码、银行、账户等词语的对话。"

def analyze_scam_with_llm(text_to_analyze: str, model_name="deepseek-chat"):
    """
    使用LLM进行深度分析，引入“合法性检查点”以降低误报率。
    """
    if not client:
        return {"error": "LLM client not available."}

    # 【核心升级】引入“合法性检查点”的全新System Prompt
    system_prompt = """
    你是一个极其严谨、注重逻辑的“对话定性分析师”，专攻反诈骗领域。误报一个正常通话是对用户的严重骚扰，必须极力避免。

    你的任务是分析一段单方面的讲话文本。在判断其是否为诈骗前，你必须先进行【合法性检查】。

    **【合法性检查点】**
    一段正常的官方或客服通话，通常会包含以下一个或多个特征。请检查文本是否符合：
    1.  **引导至官方渠道 (Official Channel Guidance)**：是否明确引导用户通过官方App、官网、小程序或线下实体网点进行操作？（例如：“详情请登录手机银行App查看”、“您可在APP内操作”、“请前往派出所办理”）
    2.  **声明无害操作 (Harmless Action Statement)**：是否明确声明本次通话不涉及收费、不要求转账、或退款会原路返回？（例如：“本次不涉及任何费用收取”、“票款将原路退回”、“我们将自动赔付您三元运费红包”）
    3.  **信息同步而非索取 (Information Sync, Not Phishing)**：通话内容主要是同步信息、提醒或通知，而没有主动索取用户的密码、验证码、银行卡详情等敏感信息？

    只有在一段话**完全不符合**上述任何合法性特征，**并且**同时表现出明确的诈骗意图（如引导添加私人微信/QQ、要求转账到安全账户、引导屏幕共享等）时，才能将其判定为诈骗。

    你的输出必须是一个严格的JSON格式对象，不要包含任何与JSON无关的文字。
    JSON对象的结构必须如下：
    {
      "legitimacy_checks": {
        "official_channel_guidance": boolean,
        "harmless_action_statement": boolean,
        "is_information_sync": boolean
      },
      "final_assessment": {
        "is_scam": boolean,
        "risk_level": "string",
        "scam_type": "string",
        "reasoning": "string"
      }
    }

    字段说明：
    - **legitimacy_checks**: 合法性检查的结果。
      - `official_channel_guidance`: 如果文本引导用户走官方渠道，则为true。
      - `harmless_action_statement`: 如果文本明确表示操作无害（不收费/原路退款），则为true。
      - `is_information_sync`: 如果文本主要是信息同步，则为true。
    - **final_assessment**: 最终评估。
      - `is_scam`: **只有在上述三项合法性检查大部分为false，且存在明确诈骗行为时，才为true。**
      - `risk_level`: 风险等级，只能是["高风险", "中风险", "低风险", "无风险"]。
      - `scam_type`: 诈骗类型，例如："冒充客服退款"、"刷单返利"、"冒充公检法"、"索要验证码"、"杀猪盘"、"未知" 或 "不适用"。
      - `reasoning`: 详细说明你做出判断的理由，必须结合【合法性检查点】的结果进行解释。
    """
    
    # 【核心升级】新的User Prompt
    user_prompt = f"请严格遵循你被设定的“对话定性分析师”角色和分析框架，对以下讲话文本进行【合法性检查】和最终评估，并严格按照要求的JSON格式返回结果。\n\n--- 讲话文本 ---\n\"{text_to_analyze}\"\n--- 结束 ---"
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"}, 
            temperature=0.0 # 对于分类和结构化输出，使用0温度以获得最稳定、可复现的结果
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"   [LLM ERROR] LLM API call failed: {e}")
        return {"error": str(e)}

def analyze_audio_for_scam(audio_path):
    print(f"-> Processing: {os.path.basename(audio_path)}...")
    result = {"filename": os.path.basename(audio_path), "transcription": "", "llm_analysis": None}
    try:
        transcription_result = asr_model.transcribe(
            audio_path, language="zh", fp16=torch.cuda.is_available(), initial_prompt=PROMPT
        )
        transcribed_text = transcription_result['text'].strip()
        result["transcription"] = transcribed_text
        if transcribed_text:
            print(f"   Transcript: \"{transcribed_text}\"")
            if client:
                print("   -> Sending to LLM for advanced analysis...")
                llm_analysis_result = analyze_scam_with_llm(transcribed_text)
                result["llm_analysis"] = llm_analysis_result
                if llm_analysis_result and "error" not in llm_analysis_result:
                    assessment = llm_analysis_result.get("final_assessment", {})
                    risk = assessment.get('risk_level', '未知')
                    scam_type = assessment.get('scam_type', '未知')
                    print(f"   [LLM Result] Risk Level: {risk}, Scam Type: {scam_type}")
                else:
                    print("   [LLM Result] Analysis failed or returned an error.")
            else:
                 print("   [LLM SKIPPED] LLM client not available.")
        else:
             print("   - Transcription is empty.")
    except Exception as e:
        print(f"   [FATAL ERROR] 无法处理文件 {os.path.basename(audio_path)}. Reason: {e}")
        result["transcription"] = f"Error: {e}"
    return result

# --- 【核心升级】全新的总结报告函数，能展示合法性检查结果 ---
def print_scam_summary_report(all_results):
    """
    生成一份详细的总结报告，包含合法性检查结果，以分析误报原因。
    """
    risk_categories = {"高风险": [], "中风险": [], "低风险": [], "无风险": [], "分析失败": []}
    
    for res in all_results:
        analysis = res.get("llm_analysis")
        if res["transcription"].startswith("Error:") or not analysis or "error" in analysis:
            risk_categories["分析失败"].append(res)
        else:
            risk_level = analysis.get("final_assessment", {}).get("risk_level", "分析失败")
            risk_categories.get(risk_level, risk_categories["分析失败"]).append(res)

    print("\n" + "="*80)
    print("           🚨  LLM 反诈骗智能分析总结报告 (V2 - 逻辑增强版)  🚨")
    print("="*80)
    print(f"总共分析了 {len(all_results)} 个音频文件。\n")

    for risk, files in risk_categories.items():
        if not files:
            continue
        
        icon = {"高风险": "🔥🔥🔥", "中风险": "⚠️", "低风险": "➡️", "无风险": "✅", "分析失败": "❌"}.get(risk)
        print(f"{icon}【{risk}】音频 ({len(files)}个)")
        
        for res in files:
            print(f"\n  📄 文件名: {res['filename']}")
            print(f"     转录内容: \"{res['transcription']}\"")
            
            analysis = res.get("llm_analysis")
            if analysis and "final_assessment" in analysis:
                assessment = analysis["final_assessment"]
                checks = analysis.get("legitimacy_checks", {})
                
                print(f"     合法性检查:")
                print(f"       - 引导至官方渠道: {checks.get('official_channel_guidance', 'N/A')}")
                print(f"       - 声明无害操作:   {checks.get('harmless_action_statement', 'N/A')}")
                print(f"       - 信息同步为主:   {checks.get('is_information_sync', 'N/A')}")
                
                print(f"     最终评估:")
                print(f"       - 诈骗类型: {assessment.get('scam_type', 'N/A')}")
                print(f"       - 判断理由: {assessment.get('reasoning', 'N/A')}")
            else:
                print("     [分析失败或格式错误]")
        print("-" * 80)
            
    print("\n报告结束。")

# --- 【核心升级】性能评估函数，适配新JSON结构 ---
def calculate_performance_metrics(all_results, scam_audio_count):
    true_positive, false_positive, true_negative, false_negative = 0, 0, 0, 0
    total_audios = len(all_results)
    
    for i, res in enumerate(all_results):
        is_true_scam = (i < scam_audio_count)
        
        is_predicted_scam = False
        llm_analysis = res.get("llm_analysis")
        if llm_analysis and isinstance(llm_analysis, dict):
            # 适配新的JSON结构
            assessment = llm_analysis.get("final_assessment", {})
            if isinstance(assessment, dict):
                is_predicted_scam = assessment.get("is_scam", False) is True
        
        if is_true_scam and is_predicted_scam: true_positive += 1
        elif not is_true_scam and is_predicted_scam: false_positive += 1
        elif not is_true_scam and not is_predicted_scam: true_negative += 1
        elif is_true_scam and not is_predicted_scam: false_negative += 1
    
    print("\n" + "="*80)
    print("                 📈  模型性能评估统计 (V2 - 逻辑增强版)  📈")
    print("="*80)
    
    print(f"测试集信息:\n  - 总样本数: {total_audios}\n  - 真实诈骗样本数 (Positive): {scam_audio_count}\n  - 真实正常样本数 (Negative): {total_audios - scam_audio_count}")
    print("-" * 40)
    print(f"混淆矩阵 (Confusion Matrix):\n  - 真正诈骗 (TP): {true_positive}\n  - 误报诈骗 (FP): {false_positive}\n  - 真正正常 (TN): {true_negative}\n  - 漏报诈骗 (FN): {false_negative}")
    print("-" * 40)
    
    accuracy = (true_positive + true_negative) / total_audios if total_audios > 0 else 0
    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) > 0 else 0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"核心性能指标:\n  - 准确率 (Accuracy): {accuracy:.2%}\n  - 精确率 (Precision): {precision:.2%}\n  - 召回率 (Recall): {recall:.2%}\n  - F1分数 (F1-Score): {f1_score:.2f}")
    print("\n" + "="*80)

# --- 3. 批量运行分析 ---
if __name__ == "__main__":
    AUDIO_DIRECTORY = "call_cases2" 
    REAL_SCAM_AUDIO_COUNT = 20 # 假设前20个是诈骗样本
    
    supported_formats = ('.wav', '.mp3', '.m4a', '.flac', '.ogg')

    if not os.path.isdir(AUDIO_DIRECTORY):
        print(f"\n错误：找不到文件夹 '{AUDIO_DIRECTORY}'。")
    elif client is None:
        print("\n程序无法继续，因为 LLM 客户端初始化失败。")
    else:
        audio_files = sorted([f for f in os.listdir(AUDIO_DIRECTORY) if f.lower().endswith(supported_formats)])
        
        if not audio_files:
            print(f"在文件夹 '{AUDIO_DIRECTORY}' 中没有找到支持的音频文件。")
        else:
            print(f"在 '{AUDIO_DIRECTORY}' 中找到 {len(audio_files)} 个音频文件，准备进行反诈骗分析...\n")
            
            all_analysis_results = []
            start_time = time.time()
            
            for filename in audio_files:
                file_path = os.path.join(AUDIO_DIRECTORY, filename)
                analysis_result = analyze_audio_for_scam(file_path)
                all_analysis_results.append(analysis_result)
            
            end_time = time.time()
            
            print_scam_summary_report(all_analysis_results)
            calculate_performance_metrics(all_analysis_results, REAL_SCAM_AUDIO_COUNT)
            
            print(f"总耗时: {end_time - start_time:.2f} 秒")