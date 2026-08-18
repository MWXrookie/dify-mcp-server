# 阶段一 · T-006 新题 50 次端到端回归测试报告

> 测试时间: 2026-08-18 15:11:51 | 输入方式: Dify 工作流自然语言声学问题

## 总体结果

| 指标 | 值 |
|------|-----|
| 总测试数 | 50 |
| 成功 | 49 |
| 失败 | 1 |
| **成功率** | **98.0%** |
| 门禁标准 | ≥ 90% |
| 门禁结果 | ✅ 通过 |

## 按类别统计

| 类别 | 成功/总数 | 成功率 | 平均耗时 | 平均重试次数 |
|------|-----------|--------|----------|-------------|
| 2D均质点源 | 9/10 | 90% | 0 ms | 0.90 |
| 2D均质初始压力 | 10/10 | 100% | 0 ms | 1.00 |
| 2D异质介质 | 10/10 | 100% | 0 ms | 1.00 |
| 传感器记录 | 10/10 | 100% | 0 ms | 1.00 |
| 边界情况 | 10/10 | 100% | 0 ms | 1.00 |

## 全部测试明细

| # | 类别 | Prompt (截断) | 结果 | 最大压力 | 耗时 | 重试 | 备注 |
|---|------|-------------|------|---------|------|------|------|
| 1 | 2D均质点源 | 在均匀水介质中模拟1.2 MHz点声源从计算域中心向外传播，声速1500 m/s，密... | ✅ | 0.3392 | 28.3s | 1 |  |
| 2 | 2D均质点源 | 做一个软组织中点声源传播仿真：声源频率2.4 MHz，声速1540 m/s，网格19... | ✅ | 0.4158 | 26.5s | 1 |  |
| 3 | 2D均质点源 | 二维均匀介质声波传播：中心点声源频率800 kHz，声速1480 m/s，网格128... | ✅ | 0.4261 | 25.9s | 1 |  |
| 4 | 2D均质点源 | 请仿真一个3 MHz点声源在水中传播，计算区域0.8cm x 0.8cm，网格224... | ✅ | 0.3838 | 20.2s | 1 |  |
| 5 | 2D均质点源 | 在1.5cm正方形区域中放置一个中心点声源，频率1.6 MHz，介质均匀声速1520... | ✅ | 0.4393 | 52.2s | 1 |  |
| 6 | 2D均质点源 | 模拟一个2.8 MHz的超声点源在均匀软组织中传播，声速1540 m/s，密度105... | ✅ | 0.4296 | 19.5s | 1 |  |
| 7 | 2D均质点源 | 均匀介质声场测试：点声源位于区域中心，频率1 MHz，声速1500 m/s，网格96... | ✅ | 0.3761 | 46.5s | 1 |  |
| 8 | 2D均质点源 | 请生成中心点声源的二维传播结果：频率2 MHz，声速1490 m/s，网格220x2... | ❌ | N/A | 23.2s | - | req_id:  PluginInvokeError: {"args":{"description":"[models] Error: Response out |
| 9 | 2D均质点源 | 水中点源仿真，频率1.75 MHz，区域1.4cm x 1.4cm，网格200x20... | ✅ | 0.4170 | 22.1s | 1 |  |
| 10 | 2D均质点源 | 做一个快速基准仿真：均匀介质，中心点声源2.2 MHz，网格144x144，区域1c... | ✅ | 0.4847 | 34.2s | 1 |  |
| 11 | 2D均质初始压力 | 模拟圆形高斯初始压力p0在均匀水介质中的传播，峰值800 Pa，标准宽度0.4mm，... | ✅ | 784.3898 | 40.5s | 1 |  |
| 12 | 2D均质初始压力 | 用初始压力场作为声源：中心高斯压力峰值1200 Pa，半宽0.7mm，软组织声速15... | ✅ | 1184.0192 | 26.5s | 1 |  |
| 13 | 2D均质初始压力 | 仿真一个偏离中心1mm的高斯p0初始压力脉冲，峰值600 Pa，半宽0.5mm，均匀... | ✅ | 593.3127 | 85.3s | 1 |  |
| 14 | 2D均质初始压力 | 二维p0声波传播：两个圆形高斯初始压力分别位于左右两侧，峰值500 Pa和700 P... | ✅ | 687.4272 | 39.0s | 1 |  |
| 15 | 2D均质初始压力 | 请模拟初始压力分布传播，p0为中心椭圆高斯，峰值900 Pa，长轴0.9mm短轴0.... | ✅ | 854.0193 | 55.5s | 1 |  |
| 16 | 2D均质初始压力 | 均匀介质中初始压力环形分布传播：环半径1.5mm，峰值400 Pa，声速1540 m... | ✅ | 1126.2814 | 28.0s | 1 |  |
| 17 | 2D均质初始压力 | 模拟一个较弱的高斯初始压力脉冲，峰值250 Pa，半宽1mm，声速1500 m/s，... | ✅ | 240.3867 | 62.4s | 1 |  |
| 18 | 2D均质初始压力 | p0初始条件测试：中心高斯峰值1500 Pa，半宽0.35mm，均匀介质声速1520... | ✅ | 1477.1908 | 32.3s | 1 |  |
| 19 | 2D均质初始压力 | 请仿真三个位于同一直线上的高斯初始压力点，峰值均为300 Pa，间距1mm，声速15... | ✅ | 232.9392 | 29.2s | 1 |  |
| 20 | 2D均质初始压力 | 模拟初始压力由一个宽高斯包络构成的声波传播，峰值1000 Pa，半宽1.2mm，网格... | ✅ | 991.9041 | 50.2s | 1 |  |
| 21 | 2D异质介质 | 模拟点声源穿过一个低声速圆形囊肿：背景声速1540 m/s，囊肿直径2.5mm且声速... | ✅ | 0.4444 | 54.4s | 1 |  |
| 22 | 2D异质介质 | 异质介质仿真：中心有一个3mm直径高声速包块，声速1800 m/s，背景1500 m... | ✅ | 0.4224 | 81.8s | 1 |  |
| 23 | 2D异质介质 | 模拟声波经过上下两层组织，上层声速1480 m/s，下层声速1650 m/s，点声源... | ✅ | 0.4012 | 41.7s | 1 |  |
| 24 | 2D异质介质 | 组织中有两个低声速囊肿，直径分别1.5mm和2mm，声速1450 m/s，背景154... | ✅ | 0.4538 | 63.8s | 1 |  |
| 25 | 2D异质介质 | 骨样区域散射仿真：右侧有一个矩形高声速区域2800 m/s，背景软组织1540 m/... | ✅ | 0.3767 | 36.4s | 1 |  |
| 26 | 2D异质介质 | 模拟一个椭圆形脂肪样低声速区域，长轴4mm短轴2mm，声速1400 m/s，背景15... | ✅ | 0.4959 | 35.0s | 1 |  |
| 27 | 2D异质介质 | 随机斑点异质介质：背景声速1500 m/s，叠加小幅空间扰动约±3%，中心点声源1.... | ✅ | 0.3352 | 56.3s | 1 |  |
| 28 | 2D异质介质 | 模拟声波从水进入软组织界面：左半区1500 m/s，右半区1540 m/s，点声源2... | ✅ | 0.4193 | 138.0s | 1 |  |
| 29 | 2D异质介质 | 含有三个小圆形高声速散射体的介质，散射体声速1700 m/s，背景1500 m/s，... | ✅ | 0.4526 | 25.4s | 1 |  |
| 30 | 2D异质介质 | 在中心圆形区域内声速逐渐从1450过渡到1600 m/s，背景1540 m/s，点声... | ✅ | 0.4176 | 40.3s | 1 |  |
| 31 | 传感器记录 | 模拟中心2 MHz点声源传播，并在右侧1mm、2mm、3mm三个位置放置传感器记录压... | ✅ | 0.3760 | 30.7s | 1 |  |
| 32 | 传感器记录 | 在均匀软组织中做传感器阵列仿真：中心1.5 MHz点声源，四个传感器位于上下左右各2... | ✅ | 0.3331 | 46.4s | 1 |  |
| 33 | 传感器记录 | 模拟一个2.2 MHz点声源，并在半径2.5mm圆周上放置6个传感器，记录各传感器峰... | ✅ | 0.4554 | 44.2s | 1 |  |
| 34 | 传感器记录 | 线阵接收测试：点源频率1 MHz，在x轴正方向每隔0.8mm放置5个传感器，声速14... | ✅ | 0.2637 | 46.9s | 1 |  |
| 35 | 传感器记录 | 请仿真四角传感器检测中心点源，点源频率2.5 MHz，声速1500 m/s，网格19... | ✅ | 0.4354 | 23.8s | 1 |  |
| 36 | 传感器记录 | 传感器记录p0传播：中心高斯初始压力峰值700 Pa，半宽0.6mm，在距离中心2m... | ✅ | 647.7082 | 69.0s | 1 |  |
| 37 | 传感器记录 | 模拟点声源在含低声速囊肿介质中的传播，并在囊肿前后各放一个传感器比较波形，点源1.8... | ✅ | 0.4392 | 92.3s | 1 |  |
| 38 | 传感器记录 | 8通道接收阵列测试：中心2 MHz点声源，8个传感器沿一条水平线均匀分布，声速150... | ✅ | 0.3838 | 33.3s | 1 |  |
| 39 | 传感器记录 | 在区域左侧放置1.5 MHz点源，右侧竖直方向放置5个传感器形成线阵，均匀介质声速1... | ✅ | 0.4409 | 40.1s | 1 |  |
| 40 | 传感器记录 | 模拟近场传感器：点源2 MHz，传感器距离声源0.5mm、1mm、1.5mm，声速1... | ✅ | 0.3638 | 39.4s | 1 |  |
| 41 | 边界情况 | 低频大波长测试：200 kHz点声源在5cm x 5cm区域中传播，声速1500 m... | ✅ | 0.2612 | 30.1s | 1 |  |
| 42 | 边界情况 | 小网格快速测试：64x64网格，区域8mm x 8mm，中心1 MHz点声源，声速1... | ✅ | 0.4230 | 28.3s | 1 |  |
| 43 | 边界情况 | 短时传播测试：2 MHz点声源，网格200x200，区域1cm，声速1500 m/s... | ✅ | 0.3638 | 59.0s | 1 |  |
| 44 | 边界情况 | 长时间传播测试：800 kHz点声源，区域2cm x 2cm，网格160x160，声... | ✅ | 0.3567 | 23.2s | 1 |  |
| 45 | 边界情况 | 高频分辨率挑战：4 MHz点声源，区域1cm x 1cm，网格256x256，声速1... | ✅ | 0.4970 | 28.6s | 1 |  |
| 46 | 边界情况 | 超小区域测试：区域3mm x 3mm，网格192x192，中心3 MHz点声源，声速... | ✅ | 0.2117 | 28.5s | 1 |  |
| 47 | 边界情况 | 靠近边界的点声源：点源距离左边界0.8mm，频率1.5 MHz，网格200x200，... | ✅ | 0.2973 | 35.3s | 1 |  |
| 48 | 边界情况 | 大区域中等网格：区域4cm x 4cm，网格192x192，点源频率700 kHz，... | ✅ | 0.4762 | 35.7s | 1 |  |
| 49 | 边界情况 | 故意设置较粗网格：点源频率3 MHz，网格80x80，区域1cm x 1cm，声速1... | ✅ | 0.9227 | 38.9s | 1 |  |
| 50 | 边界情况 | 高声速介质边界测试：均匀介质声速2200 m/s，点源1.5 MHz，网格200x2... | ✅ | 0.3018 | 30.2s | 1 |  |

## 失败分析

### #8 2D均质点源

- **Prompt**: 请生成中心点声源的二维传播结果：频率2 MHz，声速1490 m/s，网格220x220，区域1.1cm见方，模拟4.5微秒。
- **Workflow Status**: failed
- **Exit Code**: N/A
- **Reason**: req_id:  PluginInvokeError: {"args":{"description":"[models] Error: Response output is missing or does not contain embeddings: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))","traceback":"Traceback (most recent call last):\n  File \"/app/storage/cwd/langgenius/tongyi-0.2.9@76eb0772e08503769a19a4161bffafb5a90c4d4e0fee17b98c57c374404deae3/.venv/lib/python3.12/site-packages/dify_plugin/interfaces/model/text_embedding_model.py\", line 152, in invoke\n    return self._invoke(model, credentials, texts, user, input_type)\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/app/storage/cwd/langgenius/tongyi-0.2.9@76eb0772e08503769a19a4161bffafb5a90c4d4e0fee17b98c57c374404deae3/models/text_embedding/text_embedding.py\", line 58, in _invoke\n    (embeddings_batch, embedding_used_tokens) = self.embed_documents(\n                                                ^^^^^^^^^^^^^^^^^^^^^\n  File \"/app/storage/cwd/langgenius/tongyi-0.2.9@76eb0772e08503769a19a4161bffafb5a90c4d4e0fee17b98c57c374404deae3/models/text_embedding/text_embedding.py\", line 179, in embed_documents\n    raise ValueError(f\"Response output is missing or does not contain embeddings: {response}\")\nValueError: Response output is missing or does not contain embeddings: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))\n\nThe above exception was the direct cause of the following exception:\n\nTraceback (most recent call last):\n  File \"/app/storage/cwd/langgenius/tongyi-0.2.9@76eb0772e08503769a19a4161bffafb5a90c4d4e0fee17b98c57c374404deae3/.venv/lib/python3.12/site-packages/dify_plugin/core/server/io_server.py\", line 96, in _execute_request_in_thread\n    self._execute_request(\n  File \"/app/storage/cwd/langgenius/tongyi-0.2.9@76eb0772e08503769a19a4161bffafb5a90c4d4e0fee17b98c57c374404deae3/.venv/lib/python3.12/site-packages/dify_plugin/plugin.py\", line 571, in _execute_request\n    response = self.dispatch(session, data)\n               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/app/storage/cwd/langgenius/tongyi-0.2.9@76eb0772e08503769a19a4161bffafb5a90c4d4e0fee17b98c57c374404deae3/.venv/lib/python3.12/site-packages/dify_plugin/core/server/router.py\", line 85, in dispatch\n    return route.func(session, data)\n           ^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/app/storage/cwd/langgenius/tongyi-0.2.9@76eb0772e08503769a19a4161bffafb5a90c4d4e0fee17b98c57c374404deae3/.venv/lib/python3.12/site-packages/dify_plugin/core/server/router.py\", line 78, in wrapper\n    return f(session, data)\n           ^^^^^^^^^^^^^^^^\n  File \"/app/storage/cwd/langgenius/tongyi-0.2.9@76eb0772e08503769a19a4161bffafb5a90c4d4e0fee17b98c57c374404deae3/.venv/lib/python3.12/site-packages/dify_plugin/core/plugin_executor.py\", line 439, in invoke_text_embedding\n    return model_instance.invoke(\n           ^^^^^^^^^^^^^^^^^^^^^^\n  File \"/app/storage/cwd/langgenius/tongyi-0.2.9@76eb0772e08503769a19a4161bffafb5a90c4d4e0fee17b98c57c374404deae3/.venv/lib/python3.12/site-packages/dify_plugin/interfaces/model/text_embedding_model.py\", line 154, in invoke\n    raise self._transform_invoke_error(e) from e\ndify_plugin.errors.model.InvokeError: [models] Error: Response output is missing or does not contain embeddings: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))\n"},"error_type":"InvokeError","message":"[models] Error: Response output is missing or does not contain embeddings: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"}
- **Stdout**: N/A
- **Stderr**: N/A

## 纠错经验缓存前后

- 测试前: `{"error": "<urlopen error [Errno 111] Connection refused>"}`
- 测试后: `{"error": "<urlopen error [Errno 111] Connection refused>"}`
