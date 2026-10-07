#!/usr/bin/env python3
import sys
from pathlib import Path

# BUSCAR EL ARCHIVO REMALLADO .STL EN EL DIRECTORIO ACTUAL
dir_act = Path.cwd()
arch_stl = next(dir_act.glob("*closed_r*.stl"), None)
dir_foam = dir_act / "foam"

if not arch_stl:
    print(f"Error: No se encontró ningún archivo .stl en '{dir_act}'")
    sys.exit(1)

# INICIALIZAR SALOME Y LOS MÓDULOS GEOM Y MESH
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
    print("Error: Este script debe ejecutarse mediante SALOME.")
    print("Comando: salome -t salome2m.py")
    sys.exit(1)

# IMPORTAR EL ARCHIVO STL EN GEOM
mesh_1 = geompy.ImportSTL(str(arch_stl))
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
geompy.addToStudy(solid, f"{arch_stl.stem}_solid")

# PASO A MÓDULO MESH PARA REMALLADO 3D CON GMSH
mesh_2 = smesh.Mesh(solid, f"Malla_{arch_stl.stem}")
GMSH_3D = mesh_2.Tetrahedron(algo=smeshBuilder.GMSH)
par_gmsh = GMSH_3D.Parameters()

# EJECUTAR REMALLADO 3D
print("Ejecutando GMSH 1D-2D-3D...")
if not mesh_2.Compute():
    print("Error al calcular la malla 3D.")
    sys.exit(1)
else:
    print("Remallado 3D generado correctamente.")

smesh.SetName(mesh_2.GetMesh(), f"Malla_{arch_stl.stem}")

# SEPARAR EN GRUPOS (a completar)

# EXPORTAR EN FORMATO .UNV
arch_out = arch_stl.stem.replace("closed_r", "mesh") + ".unv"
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