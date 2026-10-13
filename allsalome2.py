#!/usr/bin/env python3
import sys
import math
from pathlib import Path

# VERIFICACIÓN DE ENTORNO Y ARCHIVOS
dir_act = Path.cwd()
dir_geo = dir_act / "0_geo_models"
dir_mesh = dir_act / "1_meshing"
arch_stl = next(dir_mesh.glob("*.stl"), None)
dir_foam = dir_mesh / "foam"

import numpy as np
import vtk

# ---------------------------------------------------------------------------
# PARÁMETROS DE DETECCIÓN DE TAPAS (inlet/outlets)
# ---------------------------------------------------------------------------
FAC_BUSQUEDA = 3.0          # radio de búsqueda de semillas = FAC_BUSQUEDA * radio inscrito
TOL_ANG      = 10.0         # grados máx. entre la normal de una cara y la de la semilla
TOL_PLANO    = 0.15         # distancia máx. al plano de la semilla, en unidades de radio
MIN_ALIN     = 0.5          # |cos| mínimo entre normal de la tapa y tangente de la centerline
RANGO_AREA   = (0.25, 4.0)  # área admitida de la tapa, en múltiplos de pi*r^2
NOMBRE_RADIO = "MaximumInscribedSphereRadius"


def leer_centerline(ruta):
    """Devuelve una lista de objetivos [(nombre, punto, tangente, radio), ...]:
    primero el inlet y luego los outlets, en el orden de las líneas del .vtk.
    El radio es el de la esfera inscrita en el extremo (aprox. el radio de la tapa)."""
    r = vtk.vtkPolyDataReader()
    r.SetFileName(str(ruta))
    r.Update()
    pd = r.GetOutput()

    arr = pd.GetFieldData().GetArray(NOMBRE_RADIO) or pd.GetPointData().GetArray(NOMBRE_RADIO)
    if arr is None:
        raise RuntimeError(f"la centerline no contiene el array '{NOMBRE_RADIO}'")

    def extremo(ids_ordenados):
        """ids_ordenados: puntos de la línea ordenados desde el extremo hacia el interior."""
        p0 = np.array(pd.GetPoint(ids_ordenados[0]))
        rad = arr.GetValue(ids_ordenados[0])
        interior = ids_ordenados[1:]
        pts = np.array([pd.GetPoint(i) for i in interior])
        d = np.linalg.norm(pts - p0, axis=1)
        j = int(np.argmax(d >= 1.5 * rad)) if (d >= 1.5 * rad).any() else len(d) - 1
        tg = p0 - pts[j]
        tg /= np.linalg.norm(tg)
        return p0, tg, rad

    lineas = pd.GetLines()
    lineas.InitTraversal()
    ids = vtk.vtkIdList()
    starts, ends = [], []
    while lineas.GetNextCell(ids):
        seq = [ids.GetId(k) for k in range(ids.GetNumberOfIds())]
        starts.append(seq)
        ends.append(seq[::-1])

    # inlet: punto de partida común (se toma la primera línea)
    p, tg, rad = extremo(starts[0])
    objetivos = [("inlet", p, tg, rad)]

    # outlets: extremo final de cada línea (sin duplicados)
    vistos = []
    for seq in ends:
        p, tg, rad = extremo(seq)
        if any(np.linalg.norm(p - q) < 1e-6 for q in vistos):
            continue
        vistos.append(p)
        objetivos.append((f"outlet_{len(vistos)}", p, tg, rad))
    return objetivos

# ---------------------------------------------------------------------------
# DETECCIÓN DE TAPAS POR CRECIMIENTO DE REGIÓN (numpy puro, sin SALOME)
# ---------------------------------------------------------------------------
from collections import defaultdict


def preparar_superficie(tris, coords_nodo):
    """tris: lista de (n1,n2,n3) con ids de nodo; coords_nodo: {id: (x,y,z)}.
    Devuelve normales unitarias, áreas, baricentros y lista de vecinos por arista."""
    ids = sorted(coords_nodo)
    pos = {n: i for i, n in enumerate(ids)}
    xyz = np.array([coords_nodo[n] for n in ids], float)
    T = np.array([[pos[n] for n in t] for t in tris])
    p = xyz[T]
    cr = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    areas = 0.5 * np.linalg.norm(cr, axis=1)
    nrm = cr / np.maximum(2.0 * areas, 1e-300)[:, None]
    bary = p.mean(axis=1)
    aristas = defaultdict(list)
    for k, (a, b, c) in enumerate(T):
        for e in ((a, b), (b, c), (c, a)):
            aristas[(min(e), max(e))].append(k)
    vecinos = [[] for _ in range(len(T))]
    for ts in aristas.values():
        if len(ts) == 2:
            vecinos[ts[0]].append(ts[1])
            vecinos[ts[1]].append(ts[0])
    return nrm, areas, bary, vecinos


def crecer_region_plana(semilla, nrm, bary, vecinos, radio):
    """Crece desde 'semilla' por caras vecinas que sean coplanares con ella.
    Compara siempre contra la normal/plano de la semilla (no contra el vecino inmediato),
    así la región no se 'escurre' por una pared curva."""
    n0, b0 = nrm[semilla], bary[semilla]
    cos_t = math.cos(math.radians(TOL_ANG))
    dmax = TOL_PLANO * radio
    region, pila = {semilla}, [semilla]
    while pila:
        k = pila.pop()
        for j in vecinos[k]:
            if j not in region and abs(nrm[j] @ n0) >= cos_t and abs((bary[j] - b0) @ n0) <= dmax:
                region.add(j)
                pila.append(j)
    return region


def detectar_tapa(punto, tangente, radio, nrm, areas, bary, vecinos):
    """Busca la tapa asociada a un extremo de la centerline.
    Devuelve (set de índices de cara, info) o (None, motivo)."""
    d = np.linalg.norm(bary - punto, axis=1)
    cand = np.where(d <= FAC_BUSQUEDA * radio)[0]
    cand = cand[np.argsort(d[cand])]
    a_ref = math.pi * radio ** 2
    vistos, mejor = set(), None
    for s in cand:
        s = int(s)
        if s in vistos:
            continue
        reg = crecer_region_plana(s, nrm, bary, vecinos, radio)
        vistos |= reg
        idx = np.fromiter(reg, int)
        A = areas[idx].sum()
        if not (RANGO_AREA[0] * a_ref <= A <= RANGO_AREA[1] * a_ref):
            continue
        n_m = (nrm[idx] * np.sign(nrm[idx] @ nrm[s])[:, None] * areas[idx, None]).sum(axis=0)
        n_m /= np.linalg.norm(n_m)
        alin = abs(float(n_m @ tangente))
        if alin < MIN_ALIN:
            continue
        c = (bary[idx] * areas[idx, None]).sum(axis=0) / A
        dist = float(np.linalg.norm(c - punto))
        puntaje = dist / radio + (1.0 - alin) + abs(A / a_ref - 1.0)   # menor = mejor
        if mejor is None or puntaje < mejor[0]:
            mejor = (puntaje, reg, dict(area=float(A), dist=dist, alin=alin, n=len(reg)))
    if mejor is None:
        return None, "ninguna región plana con el área y la orientación esperadas cerca del extremo"
    return mejor[1], mejor[2]


# VERIFICACIÓN INICIAL DE LA CENTERLINE
arch_cl = next(iter(sorted(dir_geo.glob("*centerlines*.vtk"))), None)
if not arch_cl:
    print(f"Error: No se encontró archivo *centerlines*.vtk en '{dir_geo}'")
    sys.exit(1)
try:
    objetivos = leer_centerline(arch_cl)
except Exception as e:
    print(f"Error: no se pudo leer la centerline '{arch_cl.name}': {e}")
    sys.exit(1)
print(f"Centerline: {arch_cl.name} -> 1 inlet, {len(objetivos) - 1} outlet(s)")

if not arch_stl:
    print(f"Error: No se encontró archivo .stl en '{dir_mesh}'")
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

# IMPORTACIÓN DE MALLA STL

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
rm_out = dir_mesh / (arch_stl.stem.replace("closed", "closed_r") + ".stl")

print(f"Exportando malla remallada a: {rm_out}")
m_princ.ExportSTL(str(rm_out))

print("Malla exportada correctamente a STL.")

arch_stl2 = next(dir_mesh.glob("*closed_r*.stl"), None)

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

# SEPARAR EN GRUPOS (tapas detectadas desde la centerline)
print("Detectando tapas a partir de los extremos de la centerline...")

# ---- Geometría de la superficie: caras, normales, baricentros, vecindad ----
face_ids = list(mesh_2.GetElementsByType(SMESH.FACE))
coords_nodo = {}
tris = []
for fid in face_ids:
    nodos = mesh_2.GetElemNodes(fid)
    for n in nodos:
        if n not in coords_nodo:
            coords_nodo[n] = mesh_2.GetNodeXYZ(n)
    tris.append(nodos[:3])           # superficie triangular (NETGEN/GMSH)
nrm, areas, bary, vecinos = preparar_superficie(tris, coords_nodo)

# ---- Una tapa por cada extremo de la centerline ----
cara_a_tapa = {}
tapas = {}
errores = []
for nombre, punto, tangente, radio in objetivos:
    region, info = detectar_tapa(punto, tangente, radio, nrm, areas, bary, vecinos)
    if region is None:
        errores.append(f"'{nombre}': {info}")
        continue
    solapadas = [cara_a_tapa[k] for k in region if k in cara_a_tapa]
    if solapadas:
        errores.append(f"'{nombre}': comparte caras con '{solapadas[0]}'")
        continue
    for k in region:
        cara_a_tapa[k] = nombre
    tapas[nombre] = region
    aviso = ""
    if info['dist'] > 2.0 * radio:
        aviso = "  [AVISO: tapa lejos del extremo, ¿unidades distintas?]"
    print(f"Parche '{nombre}' asignado (caras: {info['n']}, área: {info['area']:.2f}, "
          f"dist. a centerline: {info['dist']:.3f}, alineación: {info['alin']:.2f}){aviso}")

if errores:
    print("Error: no se pudo detectar la tapa de:")
    for e in errores:
        print("  -", e)
    print("Ajusta TOL_ANG / TOL_PLANO / MIN_ALIN / RANGO_AREA al inicio del script.")
    sys.exit(1)

# ---- Grupos de SMESH: tapas + wall (todo lo demás) ----
for nombre, region in tapas.items():
    g = mesh_2.CreateEmptyGroup(SMESH.FACE, nombre)
    g.Add([face_ids[k] for k in sorted(region)])

ids_wall = [fid for k, fid in enumerate(face_ids) if k not in cara_a_tapa]
if ids_wall:
    wall = mesh_2.CreateEmptyGroup(SMESH.FACE, "wall")
    wall.Add(ids_wall)
    print(f"Parche 'wall' asignado ({len(ids_wall)} caras)")
else:
    print("Error: no quedaron caras para 'wall'.")
    sys.exit(1)

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
