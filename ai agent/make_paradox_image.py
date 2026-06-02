from PIL import Image, ImageDraw, ImageFont
import os

W, H = 900, 680
img = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(img)

# 폰트 찾기
def find_font(size):
    candidates = [
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/NanumGothic.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

bold   = find_font(32)
bold_s = find_font(26)
mid    = find_font(20)
sm     = find_font(16)
xs     = find_font(14)

RED   = "#C0392B"
BLUE  = "#2C5F9E"
DARK  = "#1a1a2e"
GRAY  = "#7f8c8d"
LRED  = "#FFF0F0"
LBLUE = "#F0F4FF"
LYEL  = "#FEF3C7"
LPING = "#FFE8E8"
CARD  = "#F8F9FA"
BORD  = "#E0E0E0"

# ── 제목 ──────────────────────────────────────────────────────
draw.text((40, 40),  "파생변수가 드러낸 역설,",              font=bold,   fill=DARK)
draw.text((40, 85),  "더 많이 보고도 더 많이 떠난 집단",     font=bold,   fill=DARK)
draw.rectangle([40, 128, 340, 132], fill="#3B6FE0")

# ── 카드 그리기 함수 ──────────────────────────────────────────
def draw_card(y, label, promo_val, nonpromo_val, tag, tag_fg, tag_bg):
    # 카드 배경
    draw.rounded_rectangle([30, y, 870, y+110], radius=12, fill=CARD, outline=BORD, width=1)

    # 항목명
    draw.text((60, y+22), label, font=bold_s, fill=DARK)

    # 프로모션 뱃지
    draw.rounded_rectangle([310, y+18, 540, y+60], radius=8, fill=LRED)
    draw.text((320, y+22), "프로모션", font=xs, fill=RED)
    draw.text((320, y+44), promo_val, font=mid, fill=RED)

    # 비프로모션 뱃지
    draw.rounded_rectangle([560, y+18, 820, y+60], radius=8, fill=LBLUE)
    draw.text((572, y+22), "비프로모션", font=xs, fill=BLUE)
    draw.text((572, y+44), nonpromo_val, font=mid, fill=BLUE)

    # 태그
    tw = draw.textlength(tag, font=xs)
    draw.rounded_rectangle([60, y+72, 60+tw+20, y+100], radius=6, fill=tag_bg)
    draw.text((70, y+75), tag, font=xs, fill=tag_fg)

draw_card(155, "이탈률",         "32.31%",   "24.01%",   "↑ 예상 방향", RED,      LPING)
draw_card(285, "평균 시청 시간", "↑ 더 높음", "↓ 더 낮음", "⚡ 역설",     "#B45309", LYEL)
draw_card(415, "장르 다양성",    "↑ 더 높음", "↓ 더 낮음", "⚡ 역설",     "#B45309", LYEL)

# ── 차이 강조 ─────────────────────────────────────────────────
draw.text((270, 555), "이탈률 차이  8.30%p", font=mid, fill=GRAY)

out = "파생변수_역설.png"
img.save(out, dpi=(180, 180))
print(f"저장 완료: {out}")
