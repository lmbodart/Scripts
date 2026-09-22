#!/usr/bin/env python3
import sys
from pathlib import Path

# BUSCAR EL ARCHIVO .STL EN EL DIRECTORIO ACTUAL
dir_act = Path.cwd()
archivos_stl = list(dir_act.glob("*.stl"))

if not archivos_stl:
    print(f"Error: No se encontró ningún archivo .stl en '{dir_act}'")
    sys.exit(1)

arch_stl = archivos_stl[0]

# INICIALIZAR SALOME Y EL MÓDULO MESH
try:
    import salome
    salome.salome_init()
    import SMESH
    from salome.smesh import smeshBuilder

    smesh = smeshBuilder.New()
except ImportError:
    print("Error: Este script debe ejecutarse mediante SALOME.")
    print("Comando: salome -t salome1m.py")
    sys.exit(1)

# IMPORTAR EL ARCHIVO STL EN MESH
print("Importando .stl en el módulo MESH...")

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
rm_out = arch_stl.stem.replace("closed*", "closed_r") + ".stl"

print(f"Exportando malla remallada a: {rm_out}")
m_princ.ExportSTL(str(rm_out))

print("Malla exportada correctamente a STL.")