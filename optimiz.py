#!/usr/bin/env python3
import sys
import math
from pathlib import Path

# 1. VERIFICACIÓN DE ENTORNO Y ARCHIVOS
dir_act = Path.cwd()
arch_stl = next(dir_act.glob("*.stl"), None)
dir_foam = dir_act / "foam"

if not arch_stl:
    print(f"Error: No se encontró archivo .stl en '{dir_act}'")
    sys.exit(1)

try:
    import salome
    salome.salome_init()
    
    import GEOM
    from salome.geom import geomBuilder
    geompy = geomBuilder.New()

    import SMESH
    from salome.smesh import smeshBuilder
    smesh = smeshBuilder.New()
except ImportError:
    print("Error: Ejecutar este script mediante SALOME usando: salome -t -b optimiz.py")
    sys.exit(1)

print(f"Procesando geometría: {arch_stl.name}")

# 2. IMPORTACIÓN DE MALLA STL

m_princ = smesh.CreateMeshesFromSTL(str(arch_stl))

if not m_princ:
    print("Error al importar la malla STL.")
    sys.exit(1)

smesh.SetName(m_princ, arch_stl.stem)

# REMALLADO 2D CON NETGEN
algo_2d = m_princ.Triangle(smeshBuilder.NETGEN_2D, geom=None)
netgen_2d_params = algo_2d.Parameters()
netgen_2d_params.SetMaxSize(0.2)
netgen_2d_params.SetMinSize(0.2)

# EJECUTAR REMALLADO
print("Ejecutando NETGEN 2D...")
if not m_princ.Compute():
    print("Error al calcular la malla remallada.")
    sys.exit(1)

# EXPORTAR MALLA COMO STL
rm_out = arch_stl.stem.replace("closed", "closed_r") + ".stl"

print(f"Exportando malla remallada a: {rm_out}")
m_princ.ExportSTL(str(rm_out))

print("Malla exportada correctamente a STL.")

arch_stl2 = next(dir_act.glob("*closed_r*.stl"), None)

# IMPORTAR EL ARCHIVO STL EN GEOM
mesh_1 = geompy.ImportSTL(str(arch_stl2))
if mesh_1 is None:
    print("Error al importar la malla STL.")
    sys.exit(1)

# CREAR SÓLIDO A PARTIR DE LA MALLA IMPORTADA
print("Creando sólido a partir de la malla importada...")
try:
    solid = geompy.MakeSolid([mesh_1])
except Exception as e:
    shells = geompy.SubShapeAll(mesh_1, geompy.ShapeType["SHELL"])
    if shells:
        solid = geompy.MakeSolid(shells)
    else:
        faces = geompy.SubShapeAll(mesh_1, geompy.ShapeType["FACE"])
        shell_n = geompy.MakeShell(faces)
        solid = geompy.MakeSolid([shell_n])

if solid is None:
    print("Error: No se pudo construir el sólido. Asegúrate de que la malla STL sea cerrada (manifold).")
    sys.exit(1)
else:
    print("Sólido creado correctamente a partir de la malla STL.")
geompy.addToStudy(solid, f"{arch_stl2.stem}_solid")

# PASO A MÓDULO MESH PARA REMALLADO 3D CON GMSH
mesh_2 = smesh.Mesh(solid, f"Malla_{arch_stl2.stem}")
GMSH_3D = mesh_2.Tetrahedron(algo=smeshBuilder.GMSH)
par_gmsh = GMSH_3D.Parameters()

# EJECUTAR REMALLADO 3D
print("Ejecutando GMSH 1D-2D-3D...")
if not mesh_2.Compute():
    print("Error al calcular la malla 3D.")
    sys.exit(1)
else:
    print("Remallado 3D generado correctamente.")

# SEPARAR EN GRUPOS
print("Ejecutando algoritmo de segmentación matemática de parches...")

# Segmentación inicial por bordes afilados mediante API nativa
raw_groups = mesh_2.FaceGroupsSeparatedByEdges(60.0)

cap_groups = []
wall_groups = []

# Inspección vectorial y topológica de cada grupo
for grp in raw_groups:
    elem_ids = grp.GetIDs()
    total_area = 0.0
    sum_nx, sum_ny, sum_nz = 0.0, 0.0, 0.0
    centroid_z_sum = 0.0

    for elem_id in elem_ids:
        norm = mesh_2.GetFaceNormal(elem_id, True)   # normal unitaria
        nodes = mesh_2.GetElemNodes(elem_id)
        pts = [mesh_2.GetNodeXYZ(n) for n in nodes]
        v1 = [pts[1][i] - pts[0][i] for i in range(3)]
        v2 = [pts[2][i] - pts[0][i] for i in range(3)]

        cross = [
            v1[1]*v2[2] - v1[2]*v2[1],
            v1[2]*v2[0] - v1[0]*v2[2],
            v1[0]*v2[1] - v1[1]*v2[0]
        ]
        area = 0.5 * math.sqrt(sum(c**2 for c in cross))

        total_area += area
        sum_nx += norm[0] * area
        sum_ny += norm[1] * area
        sum_nz += norm[2] * area
        centroid_z_sum += (sum(p[2] for p in pts) / 3.0) * area

    if total_area == 0:
        wall_groups.append(grp)   # grupo degenerado: va a la pared
        continue

    planarity_index = math.sqrt(sum_nx**2 + sum_ny**2 + sum_nz**2) / total_area
    avg_centroid_z = centroid_z_sum / total_area

    if planarity_index >= 0.85:
        cap_groups.append({
            'group': grp,
            'area': total_area,
            'planarity': planarity_index,
            'z_center': avg_centroid_z
        })
    else:
        wall_groups.append(grp)

# Unir todos los grupos no planares en un único "wall"
if len(wall_groups) > 1:
    wall = mesh_2.UnionListOfGroups(wall_groups, "wall")
    for g in wall_groups:
        mesh_2.RemoveGroup(g)          # evita caras duplicadas en el UNV
elif len(wall_groups) == 1:
    wall = wall_groups[0]
    wall.SetName("wall")
else:
    wall = None
    print("   [!] No se encontró ningún grupo de pared.")

if wall is not None:
    print(f"   [+] Parche 'wall' asignado ({len(wall_groups)} grupos unidos)")

# Ordenamiento de tapas a lo largo del eje Z
cap_groups.sort(key=lambda x: x['z_center'])

for idx, cap_info in enumerate(cap_groups):
    name = "inlet" if idx == 0 else f"outlet_{idx}"
    cap_info['group'].SetName(name)
    print(f"   [+] Parche '{name}' asignado (Planaridad P: {cap_info['planarity']:.4f}, "
          f"Área: {cap_info['area']:.2f}, Z: {cap_info['z_center']:.2f})")

# EXPORTAR EN FORMATO .UNV
arch_out = arch_stl2.stem.replace("closed_r", "mesh") + ".unv"
p_unv = (dir_foam / arch_out).resolve()

print(f"Exportando malla a: {p_unv}")

try:
    mesh_2.ExportUNV(str(p_unv))
except Exception as e:
    print(f"Error al exportar la malla a UNV: {e}")
    sys.exit(1)

if p_unv.exists() and p_unv.stat().st_size > 0:
    print("Malla exportada correctamente a UNV.")
else:
    print("Error: el archivo UNV no se generó o está vacío.")
    sys.exit(1)



 

