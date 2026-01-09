import os
import time
import geopandas as gpd
import osmnx as ox
import pandas as pd
import networkx as nx
from shapely.geometry import MultiPolygon, Polygon
import csv

# ========== 参数设置 ==========
shp_path = "data/中国市级经纬范围/中国_市.shp"  # 输入路径
save_dir = "data/城市道路网络数据"  # 输出路径
os.makedirs(save_dir, exist_ok=True)

network_type = "drive_service"      # 路网类型
simplify_tolerance = 0.01           # 边界简化
encoding_type = "utf-8"             # 如果乱码可改为 "gb18030"

# ========== 1. 读取城市边界 ==========
china_cities = gpd.read_file(shp_path, encoding=encoding_type)
print(f"成功读取 {len(china_cities)} 个城市")
# 投影为米制坐标（计算面积用）
china_cities_proj = china_cities.to_crs(epsg=3857)

# ========== 2. 定义辅助函数 ==========
def get_city_polygon(geom, tolerance=0.01):
    """从geometry中取最大Polygon并可选简化"""
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    if tolerance:
        geom = geom.simplify(tolerance, preserve_topology=True)
    return geom

def largest_connected_component(G):
    """使用 networkx 提取最大连通子图"""
    # 提取所有连通子图
    components = list(nx.connected_components(G))
    # 找到最大的连通子图
    largest_component = max(components, key=len)
    # 从原图中提取出最大连通子图
    G_main = G.subgraph(largest_component).copy()
    return G_main

# ========== 3. 初始化 CSV 文件 ==========
csv_path = os.path.join(save_dir, "city_road_stats.csv")

# 定义表头
header = ["city", "status", "nodes", "edges", "area_km2"]


if os.path.exists(csv_path):
    existing_records = pd.read_csv(csv_path)
    downloaded_cities = set(existing_records.loc[existing_records["status"] == "success", "city"])
    print(f"📂 已存在记录 {len(downloaded_cities)} 个成功城市，将跳过这些城市。")
else:
    downloaded_cities = set()

# ========== 4. 主循环：下载路网并记录信息 ==========
for idx, row in china_cities.iterrows():
    name = row["name"] if "name" in row else row["NAME"]
    name = str(name).strip()
    save_path = os.path.join(save_dir, f"{name}.graphml")

    if name in downloaded_cities or os.path.exists(save_path):
        print(f"⏭️ 跳过 {name}（已存在数据）")
        continue
    # 获取城市面积（m² → km²）
    geom_proj = china_cities_proj.iloc[idx].geometry
    # geom_proj = row.geometry
    area_km2 = geom_proj.area / 1e6

    # 逐个城市写入 CSV
    try:
        geom = get_city_polygon(row.geometry, simplify_tolerance)
        print(f"⬇️ 正在下载 {name} 的路网...")

        # 下载 OSM 路网，返回有向图
        G = ox.graph_from_polygon(geom, network_type=network_type)

        # 将图转换为无向图
        G = G.to_undirected()

        # 使用 networkx 提取最大连通子图
        G_main = largest_connected_component(G)

        # 将最大连通子图保存为 graphml 格式
        ox.save_graphml(G_main, save_path)

        n_nodes, n_edges = len(G_main.nodes), len(G_main.edges)
        print(f"✅ {name} 下载完成，节点数：{n_nodes}, 边数：{n_edges}\n")

        record = {
            "city": name,
            "status": "success",
            "nodes": n_nodes,
            "edges": n_edges,
            "area_km2": area_km2
        }

    except Exception as e:
        print(f"❌ {name} 下载失败：{e}")
        record = {
            "city": name,
            "status": f"failed: {e}",
            "nodes": None,
            "edges": None,
            "area_km2": area_km2
        }

    # 逐个写入 CSV，跳过表头
    with open(csv_path, mode='a', newline='', encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        # 如果文件为空，写入表头
        if f.tell() == 0:
            writer.writeheader()
        writer.writerow(record)

    time.sleep(3)

print(f"🎯 所有城市处理完成，统计结果已保存至 {csv_path}")