"""创建程序图标"""
import struct
import zlib

def create_icon():
    """创建一个简单的 ICO 图标文件"""
    # 图标数据（16x16 像素，简单设计）
    width, height = 16, 16
    
    # 创建简单的 QCC 图标图案
    # 蓝色背景 + 白色文字 "Q"
    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            # 计算距离中心的距离
            cx, cy = width // 2, height // 2
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            
            # 圆形区域
            if dist < 6:
                # 内部 - 深蓝色
                row.append((0, 71, 171, 255))  # #0047AB
            elif dist < 7:
                # 边框 - 白色
                row.append((255, 255, 255, 255))
            else:
                # 外部 - 透明
                row.append((0, 0, 0, 0))
        pixels.append(row)
    
    # 转换为字节数据
    pixel_data = bytearray()
    for row in pixels:
        for r, g, b, a in row:
            pixel_data.extend([b, g, r, a])  # BGRA 格式
    
    # 创建 ICO 文件结构
    # ICO 头
    ico_header = struct.pack('<HHH', 0, 1, 1)  # 保留, 类型(1=ICO), 图像数量
    
    # 图像条目
    image_entry = struct.pack('<BBBBHHII', 
                              width, height,  # 宽高
                              0,              # 调色板
                              0,              # 保留
                              1,              # 颜色平面
                              32,             # 位深度
                              len(pixel_data) + 40,  # 数据大小
                              22              # 数据偏移
    )
    
    # BMP 信息头
    bmp_header = struct.pack('<IiiHHIIiiII',
                             40,             # 头大小
                             width,          # 宽度
                             height * 2,     # 高度（包含掩码）
                             1,              # 颜色平面
                             32,             # 位深度
                             0,              # 压缩
                             len(pixel_data), # 图像大小
                             0, 0,           # 分辨率
                             0, 0            # 颜色数
    )
    
    # 写入文件
    with open('d:/QCC/installer/icon.ico', 'wb') as f:
        f.write(ico_header)
        f.write(image_entry)
        f.write(bmp_header)
        f.write(pixel_data)
    
    print('Icon created: d:/QCC/installer/icon.ico')

if __name__ == '__main__':
    create_icon()
