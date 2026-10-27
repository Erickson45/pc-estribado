"""Desenha o mascote do PC Estribado (monitor de óculos escuros segurando a vassoura)
e salva icone.ico (pro .exe) e web/mascote.png (pra interface)."""
import math
import os

from PIL import Image, ImageDraw

AQUI = os.path.dirname(os.path.abspath(__file__))
K = 2  # desenha em 2048px e reduz no final, pra ficar com bordas lisas
S = 1024 * K

ESCURO = (13, 20, 32)
CLARO = (242, 245, 249)
TELA = (19, 32, 47)
VERDE = (56, 217, 169)
AZUL = (91, 156, 255)
MADEIRA = (150, 96, 48)
PALHA = (245, 184, 74)
PALHA_ESCURA = (196, 132, 30)
CONTORNO = 22


def p(*valores):
    return [v * K for v in valores]


def degrade(tamanho, cor1, cor2):
    """Degradê na diagonal, do canto de cima à esquerda pro de baixo à direita."""
    pequeno = Image.new("RGB", (64, 64))
    for y in range(64):
        for x in range(64):
            t = (x + y) / 126
            pequeno.putpixel((x, y), tuple(int(a + (b - a) * t) for a, b in zip(cor1, cor2)))
    return pequeno.resize((tamanho, tamanho), Image.BILINEAR)


def lente(x0, y0, x1, y1, inclina):
    """Lente estilo aviador: topo reto, fundo arredondado e mais caído pro lado de fora."""
    cx, rx, ry = (x0 + x1) / 2, (x1 - x0) / 2, y1 - y0
    pontos = [(x0, y0), (x1, y0)]
    for i in range(41):
        a = math.pi * i / 40
        x = cx + rx * math.cos(a)
        queda = inclina * (x - cx) / rx  # positivo = desce mais à direita
        pontos.append((x, y0 + ry * 0.35 + (ry * 0.65 + queda) * math.sin(a)))
    return [(px * K, py * K) for px, py in pontos]


def estrela(d, cx, cy, r, cor):
    pontos = []
    for i in range(8):
        a = math.pi / 4 * i - math.pi / 2
        raio = r if i % 2 == 0 else r * 0.28
        pontos.append(((cx + raio * math.cos(a)) * K, (cy + raio * math.sin(a)) * K))
    d.polygon(pontos, fill=cor)


def desenhar():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # Fundo: quadrado arredondado com o degradê do app
    mascara = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(p(40, 40, 984, 984), radius=220 * K, fill=255)
    img.paste(degrade(S, VERDE, AZUL), (0, 0), mascara)
    d = ImageDraw.Draw(img)

    estrela(d, 160, 170, 62, (255, 255, 255))
    estrela(d, 250, 110, 26, (255, 255, 255, 220))

    # Pé do monitor
    d.rectangle(p(462, 700, 562, 800), fill=(201, 211, 223), outline=ESCURO, width=CONTORNO * K)
    d.rounded_rectangle(p(342, 785, 682, 850), radius=30 * K, fill=CLARO, outline=ESCURO, width=CONTORNO * K)

    # Braço esquerdo na cintura (pose de malandro)
    d.line(p(200, 470, 120, 560, 190, 625), fill=ESCURO, width=30 * K, joint="curve")

    # Corpo do monitor e tela
    d.rounded_rectangle(p(190, 190, 834, 720), radius=70 * K, fill=CLARO, outline=ESCURO, width=CONTORNO * K)
    d.rounded_rectangle(p(240, 240, 784, 660), radius=40 * K, fill=TELA)
    d.ellipse(p(158, 593, 222, 657), fill=CLARO, outline=ESCURO, width=14 * K)  # mão na cintura

    # Óculos escuros com reflexo
    lentes = [lente(268, 350, 498, 520, -18), lente(526, 350, 756, 520, 18)]
    camada = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dc = ImageDraw.Draw(camada)
    for l in lentes:
        dc.polygon(l, fill=(6, 8, 12))
    brilho = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    db = ImageDraw.Draw(brilho)
    for x in (300, 558):
        db.polygon(p(x + 40, 365, x + 85, 365, x + 15, 470, x - 30, 470), fill=(255, 255, 255, 150))
        db.polygon(p(x + 110, 365, x + 130, 365, x + 60, 470, x + 40, 470), fill=(255, 255, 255, 90))
    so_lentes = Image.new("L", (S, S), 0)
    for l in lentes:
        ImageDraw.Draw(so_lentes).polygon(l, fill=255)
    camada.paste(brilho, (0, 0), Image.composite(brilho.getchannel("A"), Image.new("L", (S, S), 0), so_lentes))
    img.alpha_composite(camada)
    d = ImageDraw.Draw(img)
    d.line(p(255, 362, 769, 362), fill=(6, 8, 12), width=30 * K)  # armação de cima
    d.line(p(490, 375, 534, 375), fill=(6, 8, 12), width=22 * K)  # ponte

    # Sorriso confiante (de lado)
    d.arc(p(410, 470, 640, 600), start=0, end=145, fill=VERDE, width=24 * K)

    # Vassoura na frente, segurada pela mão direita
    topo, base = (905, 225), (775, 830)
    dx, dy = base[0] - topo[0], base[1] - topo[1]
    comp = math.hypot(dx, dy)
    ux, uy = dx / comp, dy / comp
    nx, ny = -uy, ux

    def ponto(dist, lado):
        return ((base[0] + ux * dist + nx * lado) * K, (base[1] + uy * dist + ny * lado) * K)

    palha = [ponto(10, -62), ponto(10, 62), ponto(150, 105), ponto(150, -105)]
    d.polygon(palha, fill=PALHA, outline=ESCURO, width=16 * K)
    for lado in (-60, -20, 20, 60):
        d.line([ponto(40, lado * 0.7), ponto(140, lado)], fill=PALHA_ESCURA, width=10 * K)
    d.line(p(*topo, *base), fill=ESCURO, width=52 * K)
    d.line(p(*topo, *base), fill=MADEIRA, width=28 * K)
    d.polygon([ponto(-20, -72), ponto(-20, 72), ponto(20, 72), ponto(20, -72)], fill=(110, 66, 28), outline=ESCURO, width=14 * K)

    # Braço direito até o cabo
    mao = (topo[0] + ux * 300, topo[1] + uy * 300)
    d.line(p(834, 500, mao[0] - 10, mao[1] - 5), fill=ESCURO, width=30 * K)
    d.ellipse(p(mao[0] - 36, mao[1] - 36, mao[0] + 36, mao[1] + 36), fill=CLARO, outline=ESCURO, width=14 * K)

    return img


def _fonte(tamanho, negrito=True):
    from PIL import ImageFont
    pasta = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for nome in (("segoeuib.ttf", "arialbd.ttf") if negrito else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(os.path.join(pasta, nome), tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def imagens_instalador(mascote):
    """Faixa lateral (boas-vindas/fim) e ícone do topo do instalador, em 3 escalas de DPI."""
    pasta = os.path.join(AQUI, "instalador")
    os.makedirs(pasta, exist_ok=True)
    for escala in (1, 1.5, 2):
        w, h = int(164 * escala), int(314 * escala)
        img = degrade(max(w, h), (11, 15, 21), (15, 61, 51)).crop((0, 0, w, h)).convert("RGB")
        m = mascote.resize((int(120 * escala),) * 2, Image.LANCZOS)
        img.paste(m, ((w - m.width) // 2, int(56 * escala)), m)
        d = ImageDraw.Draw(img)
        for texto, y, fonte, cor in (("PC Estribado", 196, _fonte(int(19 * escala)), (231, 237, 244)),
                                     ("leve, liso e", 228, _fonte(int(12 * escala), False), (138, 151, 168)),
                                     ("sem travar", 246, _fonte(int(12 * escala), False), (138, 151, 168))):
            largura = d.textlength(texto, font=fonte)
            d.text(((w - largura) / 2, y * escala), texto, font=fonte, fill=cor)
        img.save(os.path.join(pasta, f"lateral{int(escala * 100)}.bmp"))
        lado = int(55 * escala)
        fundo = Image.new("RGB", (lado, lado), (255, 255, 255))
        icone = mascote.resize((lado, lado), Image.LANCZOS)
        fundo.paste(icone, (0, 0), icone)
        fundo.save(os.path.join(pasta, f"icone{int(escala * 100)}.bmp"))


def main():
    grande = desenhar().resize((1024, 1024), Image.LANCZOS)
    grande.save(os.path.join(AQUI, "icone.ico"),
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    grande.resize((256, 256), Image.LANCZOS).save(os.path.join(AQUI, "web", "mascote.png"))
    grande.save(os.path.join(AQUI, "icone_1024.png"))
    imagens_instalador(grande)
    print("Ícone e imagens do instalador gerados.")


if __name__ == "__main__":
    main()
