#!/usr/bin/env python3
"""Recorta los extremos de un modelo VTK con un plano por cada extremo de la centerline.
Uso: recorte.py modelo.vtk centerlines.vtk salida.vtk [--factor 0.0]"""
import argparse
import numpy as np
import vtk

N_RADIO = "MaximumInscribedSphereRadius"

def leer_centerline(ruta):
    r = vtk.vtkPolyDataReader()
    r.SetFileName(str(ruta))
    r.Update()
    pd = r.GetOutput()
    arr = pd.GetFieldData().GetArray(N_RADIO) or pd.GetPointData().GetArray(N_RADIO)
    if arr is None:
        raise RuntimeError(f"la centerline no contiene el array '{N_RADIO}'")

    def extremo(ids):
        p0 = np.array(pd.GetPoint(ids[0]))
        rad = arr.GetValue(ids[0])
        pts = np.array([pd.GetPoint(i) for i in ids[1:]])
        d = np.linalg.norm(pts - p0, axis=1)
        j = int(np.argmax(d >= 1.5 * rad)) if (d >= 1.5 * rad).any() else len(d) - 1
        tg = p0 - pts[j]
        return p0, tg / np.linalg.norm(tg), rad

    lineas = pd.GetLines()
    lineas.InitTraversal()
    ids = vtk.vtkIdList()
    starts, ends = [], []
    while lineas.GetNextCell(ids):
        seq = [ids.GetId(k) for k in range(ids.GetNumberOfIds())]
        starts.append(seq)
        ends.append(seq[::-1])

    objetivos = [("inlet", *extremo(starts[0]))]
    vistos = []
    for seq in ends:
        p, tg, rad = extremo(seq)
        if any(np.linalg.norm(p - q) < 1e-6 for q in vistos):
            continue
        vistos.append(p)
        objetivos.append((f"outlet_{len(vistos)}", p, tg, rad))
    return objetivos

from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk

def recortar(pd, p, tg, rad, factor, lat_max=2.0):
    """Corta solo la boca del extremo: el plano (perpendicular a tg, desplazado
    'factor' radios hacia el interior) actúa únicamente en puntos cuya distancia
    al eje del extremo sea < lat_max*rad. El resto del modelo no se toca."""
    xyz = vtk_to_numpy(pd.GetPoints().GetData())
    v = xyz - p
    a = v @ tg                                   # posición axial (+ hacia afuera)
    lat = np.linalg.norm(v - np.outer(a, tg), axis=1)
    s = (-factor * rad) - a                      # >0 = se conserva
    s[lat >= lat_max * rad] = rad                # fuera de la zona: se conserva
    arr = numpy_to_vtk(s, deep=True)
    arr.SetName("clip_s")
    pd.GetPointData().SetScalars(arr)

    clip = vtk.vtkClipPolyData()
    clip.SetInputData(pd)
    clip.SetValue(0.0)                           # conserva s > 0
    clip.Update()
    out = vtk.vtkPolyData()
    out.DeepCopy(clip.GetOutput())
    out.GetPointData().RemoveArray("clip_s")
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modelo")
    ap.add_argument("centerline")
    ap.add_argument("salida")
    ap.add_argument("--factor", type=float, default=0.5,
                help="desplazamiento del plano hacia el interior, en radios")
    a = ap.parse_args()

    rd = vtk.vtkPolyDataReader()
    rd.SetFileName(a.modelo)
    rd.Update()
    pd = rd.GetOutput()

    for nombre, p, tg, rad in leer_centerline(a.centerline):
        pd = recortar(pd, p, tg, rad, a.factor)
        print(f"{nombre}: corte a {a.factor} radios dentro del extremo (radio {rad:.3f})")

    cf = vtk.vtkPolyDataConnectivityFilter()
    cf.SetInputData(pd)
    cf.SetExtractionModeToLargestRegion()
    cf.Update()
    cl = vtk.vtkCleanPolyData()
    cl.SetInputData(cf.GetOutput())
    cl.Update()

    wr = vtk.vtkPolyDataWriter()
    wr.SetFileName(a.salida)
    wr.SetInputData(cl.GetOutput())
    wr.Write()
    print(f"Guardado: {a.salida}")


if __name__ == "__main__":
    main()