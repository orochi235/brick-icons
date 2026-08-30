"""Dihedral angle at every curved-surface junction, per part."""
import sys, math
import numpy as np
from brick_icons import occt, hlr
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
from OCP.TopExp import TopExp
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.GeomLProp import GeomLProp_SLProps
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf


def normal_at(face, edge):
    f = TopoDS.Face_s(face)
    c = BRepAdaptor_Curve(edge)
    pt = c.Value((c.FirstParameter() + c.LastParameter()) / 2.0)
    surf = BRep_Tool.Surface_s(f)
    proj = GeomAPI_ProjectPointOnSurf(pt, surf)
    if proj.NbPoints() < 1:
        return None
    u, v = proj.LowerDistanceParameters()
    props = GeomLProp_SLProps(surf, u, v, 1, 1e-6)
    if not props.IsNormalDefined():
        return None
    n = props.Normal()
    return np.array([n.X(), n.Y(), n.Z()])


def run(part, ldraw):
    out = occt.flatten_part(part, ldraw)
    shape = occt.build_shape(out)
    amap = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_ShapeEnum.TopAbs_EDGE,
                                   TopAbs_ShapeEnum.TopAbs_FACE, amap)
    rows = []
    for i in range(1, amap.Extent() + 1):
        faces = list(amap.FindFromIndex(i))
        if len(faces) != 2 or faces[0].IsSame(faces[1]):
            continue
        try:
            kinds = [BRepAdaptor_Surface(TopoDS.Face_s(f)).GetType() for f in faces]
        except Exception:
            continue
        if not any(k in occt.CURVED for k in kinds):
            continue
        edge = TopoDS.Edge_s(amap.FindKey(i))
        a, b = normal_at(faces[0], edge), normal_at(faces[1], edge)
        if a is None or b is None:
            continue
        c = float(np.clip(abs(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b)), 0, 1))
        ang = math.degrees(math.acos(c))
        ad = BRepAdaptor_Curve(edge)
        r = ad.Circle().Radius() if ad.GetType() == GeomAbs_CurveType.GeomAbs_Circle else None
        rows.append((round(ang, 1), None if r is None else round(r, 1)))
    return rows


if __name__ == "__main__":
    ldraw = sys.argv[1]
    for part in sys.argv[2:]:
        rows = run(part, ldraw)
        angs = sorted(set(a for a, _ in rows))
        print(f"{part}: {len(rows)} curved junctions; distinct angles {angs[:20]}", flush=True)
