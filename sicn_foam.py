#!/usr/bin/env python3
"""
SICN (Signed Inverse Condition Number) sobre la malla interna de un caso OpenFOAM.
Evalua tetraedros y prismas triangulares (wedge). Otras celdas (poliedros, hexas) se saltan.

Uso (pvpython o python con vtk):
  pvpython sicn_foam.py caso.foam [--umbral 0.2] [--salida calidad]

Salida: <prefijo>_sicn.vtu -> abrir en ParaView y colorear por SICN (o por 'malo').
"""
import argparse
import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk

TET, WEDGE = 10, 13          # tipos VTK
S3 = np.sqrt(3.0)
# Matrices del elemento ideal (columnas = aristas desde el vertice)
W_TET = np.array([[1, .5, .5], [0, S3 / 2, S3 / 6], [0, 0, np.sqrt(2 / 3)]])
W_WED = np.array([[1, .5, 0], [0, S3 / 2, 0], [0, 0, 1.0]])
# True: en prismas, la altura se iguala a la arista de la base para medir solo
# la deformacion (sesgo), sin penalizar que las capas limite sean delgadas.
NORMALIZAR_ALTURA = True


def sicn_3d(A, W):
    """A: (N,3,3) con aristas en columnas. SICN = 3 / (||T||_F * ||T^-1||_F) * signo(det T)."""
    T = A @ np.linalg.inv(W)
    det = np.linalg.det(T)
    ok = np.abs(det) > 1e-300
    Ts = np.where(ok[:, None, None], T, np.eye(3))
    k = np.linalg.norm(Ts, axis=(1, 2)) * np.linalg.norm(np.linalg.inv(Ts), axis=(1, 2))
    s = 3.0 / k * np.sign(det)
    s[~ok] = 0.0
    return s


def sicn_tets(P):
    A = np.stack([P[:, 1] - P[:, 0], P[:, 2] - P[:, 0], P[:, 3] - P[:, 0]], axis=2)
    s = sicn_3d(A, W_TET)
    return -s if np.median(s) < 0 else s      # corrige convencion de orientacion del lector


def sicn_wedges(P):
    out = []
    for off in (0, 3):                         # 3 esquinas de la base inferior y 3 de la superior
        for c in range(3):
            c0, c1, c2 = off + c, off + (c + 1) % 3, off + (c + 2) % 3
            a, b = P[:, c1] - P[:, c0], P[:, c2] - P[:, c0]
            v = P[:, 3 + c] - P[:, c]          # siempre de abajo hacia arriba
            if NORMALIZAR_ALTURA:
                lb = 0.5 * (np.linalg.norm(a, axis=1) + np.linalg.norm(b, axis=1))
                v = v * (lb / np.maximum(np.linalg.norm(v, axis=1), 1e-300))[:, None]
            out.append(sicn_3d(np.stack([a, b, v], axis=2), W_WED))
    if np.median(out[0]) < 0:
        out = [-o for o in out]
    return np.min(out, axis=0)                 # peor esquina


def _llamar(obj, metodo, *args):
    """Llama obj.metodo(*args) solo si existe en esta version de VTK."""
    f = getattr(obj, metodo, None)
    if f is None:
        print(f"Aviso: este VTK no tiene {metodo}; se usa el valor por defecto.")
        return False
    f(*args)
    return True


def _primer_ugrid(obj):
    """Baja por los bloques de un multibloque hasta el primer vtkUnstructuredGrid."""
    if obj is None:
        return None
    if obj.IsA("vtkUnstructuredGrid"):
        return obj
    if hasattr(obj, "GetNumberOfBlocks"):
        for i in range(obj.GetNumberOfBlocks()):
            ug = _primer_ugrid(obj.GetBlock(i))
            if ug is not None:
                return ug
    return None


def leer_malla(ruta):
    r = vtk.vtkOpenFOAMReader()
    r.SetFileName(ruta)
    _llamar(r, "SetSkipZeroTime", 0)           # incluir el tiempo 0 (snappy -overwrite no crea otros)
    r.UpdateInformation()
    _llamar(r, "SetDecomposePolyhedra", 0)     # no partir los poliedros (si esta disponible)
    _llamar(r, "SetCreateCellToPoint", 0)
    # Solo geometria: no leer campos (evita errores por 'includeEtc' en 0/)
    _llamar(r, "DisableAllCellArrays")
    _llamar(r, "DisableAllPointArrays")
    _llamar(r, "DisableAllLagrangianArrays")
    _llamar(r, "DisableAllPatchArrays")
    _llamar(r, "SetPatchArrayStatus", "internalMesh", 1)
    t = r.GetTimeValues()
    if t.GetNumberOfTuples():
        r.SetTimeValue(t.GetValue(t.GetNumberOfTuples() - 1))
    r.Update()
    ug = _primer_ugrid(r.GetOutput())
    if ug is None:
        raise RuntimeError("no se pudo leer el internalMesh del caso OpenFOAM")
    return ug


def agregar(ug, nombre, arr):
    a = numpy_to_vtk(arr, deep=True)
    a.SetName(nombre)
    ug.GetCellData().AddArray(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("foam")
    ap.add_argument("--umbral", type=float, default=0.2, help="SICN por debajo = malo")
    ap.add_argument("--salida", default="calidad")
    a = ap.parse_args()

    ug = leer_malla(a.foam)
    n = ug.GetNumberOfCells()
    pts = vtk_to_numpy(ug.GetPoints().GetData())
    tipos = vtk_to_numpy(ug.GetCellTypesArray())
    cells = ug.GetCells()
    off = vtk_to_numpy(cells.GetOffsetsArray())
    con = vtk_to_numpy(cells.GetConnectivityArray())

    sicn = np.full(n, np.nan)
    for tipo, nv, f in ((TET, 4, sicn_tets), (WEDGE, 6, sicn_wedges)):
        idx = np.where(tipos == tipo)[0]
        if len(idx) == 0:
            continue
        P = pts[con[off[idx][:, None] + np.arange(nv)]]
        sicn[idx] = f(P)

    ev = ~np.isnan(sicn)
    print(f"Celdas totales: {n}")
    for t, nom in ((TET, "tetraedros"), (WEDGE, "prismas")):
        m = tipos == t
        if m.any():
            print(f"  {nom}: {m.sum()}  SICN min {sicn[m].min():.3f}  media {sicn[m].mean():.3f}")
    print(f"  no evaluadas (poliedros/otras): {(~ev).sum()}")

    malo = ev & (sicn < a.umbral)
    print(f"Celdas con SICN < {a.umbral}: {malo.sum()}  (invertidas, SICN <= 0: {(ev & (sicn <= 0)).sum()})")

    agregar(ug, "SICN", sicn)                  # NaN en celdas no evaluadas
    agregar(ug, "malo", malo.astype(np.uint8))
    w = vtk.vtkXMLUnstructuredGridWriter()
    w.SetFileName(f"{a.salida}_sicn.vtu")
    w.SetInputData(ug)
    w.Write()
    print(f"Escrito: {a.salida}_sicn.vtu")


if __name__ == "__main__":
    main()
