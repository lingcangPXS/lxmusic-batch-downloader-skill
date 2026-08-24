# 洛雪音乐批量下载器 🎵

将「歌名 + 歌手」的清单，批量变成电脑里的**无损音乐文件（FLAC）**+ 配套歌词（.lrc）。支持按分类自动归档、同歌手相邻整理、生成下载报告。

---

## 📦 包里有什么？

| 文件 | 说明 |
|------|------|
| `SKILL.md` | Skill 主文档（含小白说明 + AI 指令流程） |
| `lxmusic_batch_downloader.py` | **唯一可运行脚本**——改几行配置即用 |
| `test_songs.txt` | 5 首典型测试歌曲（覆盖流行/摇滚/国风/配乐/英文） |
| `manifest.json` | 元数据（名称/版本/依赖/目录结构） |
| `import_skill.ps1` | Windows 一键导入脚本 |
| `import_skill.sh` | Linux/Mac 一键导入脚本 |

---

## ⚡ 快速上手（3 分钟搞定）

### 第一步：安装洛雪助手（必需）
- 打开 https://lxmusic.toside.cn/ 下载 Windows 版并安装
- 打开洛雪 → **设置 → 开放 API** → 勾选 **"启用开放 API"**
- **记一下端口号**（默认 23330，若被修改过以实际显示为准）

### 第二步：导入自定义音乐源
- 洛雪 → **设置 → 自定义源管理** → 添加 `.js` 音源文件（如墨澜音乐源等聚合音源）

### 第三步：安装 Python 依赖
```bash
pip install requests pypinyin
```

### 第四步：开始下载！

```bash
# ── 方法 A：交互式引导（推荐新手，有选择题帮你选）──
python lxmusic_batch_downloader.py

# ── 方法 B：直接指定文件路径（老手速通）──
python lxmusic_batch_downloader.py --list "我的歌单.txt"

# ── 方法 C：先试跑 5 首验证链路（最安全）──
python lxmusic_batch_downloader.py --test

# ── 方法 D：试运行，不真下载只看看能搜到多少──
python lxmusic_batch_downloader.py --dry

# ── 方法 E：仅对已有目录做"同歌手相邻 + 连续编号"整理──
python lxmusic_batch_downloader.py --reorder-all
```

---

## ⚙️ 定制参数（改开头 USER_CONFIG 字典）

| 参数 | 作用 | 默认值 |
|------|------|--------|
| `lx_port` | 洛雪开放 API 端口 | 23330 |
| `playlist_file` | 歌单文件路径 | 留空则交互式输入 |
| `output_dir` | 输出文件夹路径 | 留空则交互式询问 |
| `quality_order` | 音质优先级列表 | ["flac24bit","flac","320k","128k"] |
| `source_order` | 平台搜索顺序 | ["kg","tx","wy","kw","mg"] |
| `workers` | 并发线程数 | 8 |
| `timeout` | 单次请求超时(秒) | 60 |
| `name_threshold` | 歌名匹配阈值 | 0.55 |

**示例：只想要纯 FLAC，用网易云优先：**
```python
"quality_order": ["flac"],
"source_order": ["wy", "tx", "kg", "kw", "mg"],
```

---

## 📊 输出结果

下载完成后在目录下生成：
- `01-华语经典流行/` —— `001-平凡之路-朴树.flac` + `001-平凡之路-朴树.lrc`
- `02-粤语港台摇滚/` —— 同上
- ……
- **`下载状态报告.csv`** —— 每首的状态、来源、音质、大小
- **`缺失清单.csv`** —— 所有找不到的歌曲，方便你单独处理

最终给用户的总结：
> ✅ 共 N 首 → 成功 X 首（Y%）、无损占比 Z%、缺失 M 首及原因

---

## ❓ 常见问题

**Q: 搜不到某首歌？**
A: 尝试换搜索顺序（如 wy,tx,kg,kw,mg），或检查歌名是否有空格/特殊字符。冷门纯配乐确实不存在于公开平台也属正常。

**Q: 为什么有些是 MP3？**
A: 该平台该歌曲没有提供无损格式，自动回退到 320k MP3。可在 quality_order 里调整。

**Q: 可以删大文件腾空间吗？**
A: **本脚本绝不删除任何音频文件**。如需清理大文件请手动操作。

**Q: 会不会泄露隐私？**
A: **不会**。所有操作本地完成，Cookie 只在内存中使用获取更高音质，不写入磁盘也不上传服务器。

---

## 🔒 安全声明

- ⚠️ 仅供个人学习研究使用
- ⚠️ 不保证所有歌曲均可下载（受平台版权限制）
- ⚠️ 请遵守当地版权法规
- ✅ **永不删除已有音频文件**
- ✅ 重命名均保留备份映射表（可随时还原）
- ✅ Cookie 不持久化存储、不上传外部服务器

---

## 📁 Skill 包结构

```
DSH插件集合/
├── SKILL.md                    ← Skill 主文档（AI 读取）
├── lxmusic_batch_downloader.py ← 核心脚本（用户运行）
├── test_songs.txt              ← 测试用例
├── manifest.json               ← 元数据
├── import_skill.ps1            ← Windows 一键导入
└── import_skill.sh             ← Linux/Mac 一键导入
```
