#!/usr/bin/env bash
# ════════════════════════════════════════════
# 洛雪音乐批量下载器 — 一键导入脚本 (Bash/Linux/Mac)
# ── 用法: chmod +x import_skill.sh && ./import_skill.sh
# ════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo ""
echo "================================================"
echo -e "${GREEN}🎵 洛雪音乐批量下载器 — 一键导入${NC}"
echo "================================================"
echo ""

# ── 来源目录（本脚本所在目录）──
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 目标目录：常见路径 ──
POSSIBLE_DEST=(
    "$HOME/.agents/skills/lxmusic-batch-downloader"
    "/home/$USER/.agents/skills/lxmusic-batch-downloader"
    "$PWD/../../.agents/skills/lxmusic-batch-downloader"
)

DEST=""
for candidate in "${POSSIBLE_DEST[@]}"; do
    if [ -d "$candidate" ]; then
        DEST="$candidate"
        break
    fi
done

if [ -z "$DEST" ]; then
    echo -e "${RED}✗ 未找到目标目录！${NC}"
    echo ""
    echo "请手动创建并运行以下命令："
    echo ""
    echo -e "  ${CYAN}mkdir -p ~/.agents/skills/lxmusic-batch-downloader${NC}"
    echo -e "  ${CYAN}cp -r $THIS_DIR/* ~/.agents/skills/lxmusic-batch-downloader/${NC}"
    echo ""
    echo "然后再次运行此脚本："
    echo -e "  ${CYAN}. $0 --force $HOME/.agents/skills/lxmusic-batch-downloader${NC}"
    exit 1
fi

echo -e "  ${CYAN}来源:${NC} $(basename "$THIS_DIR")/"
echo -e "  ${CYAN}目标:${NC} $(basename "$DEST")/"
echo ""

# ── 检查核心文件是否存在 ──
MISSING=()
for f in "SKILL.md" "lxmusic_batch_downloader.py"; do
    if [ ! -f "$THIS_DIR/$f" ]; then
        MISSING+=("$f")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo -e "${YELLOW}⚠️  缺少核心文件: ${MISSING[*]}${NC}"
    echo "   请确保所有文件都在同一目录下。"
    exit 1
fi

# ── 执行复制 ──
if [ -n "$DEST" ]; then
    # 备份旧版本
    EXISTING=$(find "$DEST" -maxdepth 1 -type f 2>/dev/null | wc -l)
    if [ "$EXISTING" -gt 0 ]; then
        BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)_old"
        cp -a "$DEST" "${DEST}_${BACKUP_NAME}"
        echo -e "${YELLOW}✓ 已备份旧版到: $(basename "$(dirname "$DEST")")_${BACKUP_NAME}/${NC}"
    fi

    # 清空再写入
    find "$DEST" -maxdepth 1 -type f -delete 2>/dev/null || true

    # 复制全部文件
    cp "$THIS_DIR"/* "$DEST"/

    echo ""
    echo "================================================"
    echo -e "${GREEN}✅ 导入成功！${NC}"
    echo "================================================"
    echo ""
    echo -e "  ${CYAN}📖 阅读说明: cd $DEST && cat README.md${NC}"
    echo -e "  ${CYAN}🧪 快速测试: python $DEST/lxmusic_batch_downloader.py --test${NC}"
fi
