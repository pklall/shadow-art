#!/usr/bin/python

from PIL import Image
import PIL.ImageOps
from solid import *
from solid.utils import *
import os
import subprocess
from subprocess import call

class scad_import( openscad_object):
    def __init__(self, f):
        openscad_object.__init__(self, 'import', {"file":f})
"""
exec(new_openscad_class_str("offset", ["delta"], ["join_type", "miter_limit"]))
"""

def genGlobalIndex():
    genGlobalIndex.counter += 1
    return genGlobalIndex.counter
genGlobalIndex.counter = 0

def imgToPolyhedron(img, channel = 3):
    """
    Creates a polyhedron from the image in the x-y plane using the specified
    channel.
    """
    points = []
    # Note that OpenSCAD requires that triangles be specified in clockwise order
    triangles = []

    size = img.size

    base = -128

    # Add corner points and base triangles
    """
    points.append([0, 0, base])
    points.append([size[0] - 1, 0, base])
    points.append([0, size[1] - 1, base])
    points.append([size[0] - 1, size[1] - 1, base])

    triangles.append([1, 2, 0])
    triangles.append([2, 1, 3])
    """
    # Add triangles for the base
    for y in range(0, size[1] - 1):
        for x in range(0, size[0] - 1):
            corners = [len(points) + i for i in range(4)]
            points.append([x, y, base])
            points.append([x + 1, y, base])
            points.append([x, y + 1, base])
            points.append([x + 1, y + 1, base])
            # Note that order for top mesh triangles is reversed from
            # that of the base mesh
            triangles.append([corners[1], corners[0], corners[2]])
            triangles.append([corners[3], corners[1], corners[2]])

    # Add triangle mesh for main part of image...

    # First, add points needed for the mesh

    coordPointMap = {}

    for y in range(0, size[1]):
        for x in range(0, size[0]):
            z = img.getpixel((x, y))[channel]
            coordPointMap[(x, y)] = len(points)
            points.append([x, y, z])

    # Add triangles for the mesh
    for y in range(0, size[1] - 1):
        for x in range(0, size[0] - 1):
            corners = [(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)]
            corners = [coordPointMap[c] for c in corners]
            # Note that order for top mesh triangles is reversed from
            # that of the base mesh
            triangles.append([corners[1], corners[0], corners[2]])
            triangles.append([corners[3], corners[1], corners[2]])

    # Add triangles for edge boundaries
    def addTrianglesForEdge(pt0, pt1):
        """
        Note that pt0 and pt1 must be (x, y) pairs along the edge of the image
        in clockwise-order.
        """
        # Add extra points on the base
        base0I = len(points)
        points.append([pt0[0], pt0[1], base])
        base1I = len(points)
        points.append([pt1[0], pt1[1], base])
        top0I = coordPointMap[pt0]
        top1I = coordPointMap[pt1]
        triangles.append([base0I, top0I, top1I])
        triangles.append([base0I, top1I, base1I])

    for y in range(0, size[1] - 1):
        pt0 = (0, y + 1)
        pt1 = (0, y)
        addTrianglesForEdge(pt0, pt1)

    for y in range(1, size[1]):
        pt0 = (size[0] - 1, y - 1)
        pt1 = (size[0] - 1, y)
        addTrianglesForEdge(pt0, pt1)

    for x in range(0, size[0] - 1):
        pt0 = (x, 0)
        pt1 = (x + 1, 0)
        addTrianglesForEdge(pt0, pt1)

    for x in range(1, size[0]):
        pt0 = (x, size[1] - 1)
        pt1 = (x - 1, size[1] - 1)
        addTrianglesForEdge(pt0, pt1)

    # FIXME 10 is completely arbitrary
    return polyhedron(points, triangles, 10)

def imgToPoly(img, channel = 3):
    heightmapFilename = "./results/heightmap_" + str(genGlobalIndex()) + ".dat"
    hfile = open(heightmapFilename, "w")
    size = img.size
    for y in range(0, size[1]):
        for x in range(0, size[0]):
            pix = img.getpixel((x, y))
            if isinstance(pix, tuple):
                z = img.getpixel((x, y))[channel]
            else:
                z = pix
            hfile.write(str(z) + " ")
        hfile.write("\n")
    hfile.close()
    maxS = max(size[0], size[1])
    return scale([maxS, maxS, 1])(
            surface(file=os.path.abspath(heightmapFilename), center=True, convexity=10)
            )

def erodeImage(img, itercount = 2):
    eimg = img.copy()
    size = img.size
    for i in range(itercount):
        tmp = img
        img = eimg
        eimg = tmp
        for y in range(0, size[1]):
            for x in range(0, size[0]):
                mval = img.getpixel((x, y))
                if x > 0:
                    mval = min(mval, img.getpixel((x - 1, y)))
                else:
                    mval = 0
                if x < size[0] - 1:
                    mval = min(mval, img.getpixel((x + 1, y)))
                else:
                    mval = 0
                if y > 0:
                    mval = min(mval, img.getpixel((x, y - 1)))
                else:
                    mval = 0
                if y < size[1] - 1:
                    mval = min(mval, img.getpixel((x, y + 1)))
                else:
                    mval = 0
                eimg.putpixel((x, y), mval)
    return eimg

def polyToOutline(poly):
    return projection(cut=True)(down(128)(poly))

def shadowVolumeFromOutlines(outlines):
    extruded = [linear_extrude(height=10000, center=True, convexity=3)(o) for o in outlines]

    extruded[0] = rotate([-90, 0, 0])(extruded[0])

    shadowVolume = intersection()([extruded[0], extruded[1]])

    return shadowVolume

def outlinesFromShadowVolume(s):
    return [projection(cut=False)(rotate([90, 0, 0])(s)), projection(cut=False)(s)]

def shadowVolumeFromImages(images, size = 32, invert = False, erode = False):
    images = [PIL.ImageOps.grayscale(img) for img in images]
    if invert:
        images = [PIL.ImageOps.invert(img) for img in images]

    if erode:
        images = [erodeImage(i, 5) for i in images]

    images = [img.resize((size, size), Image.ANTIALIAS) for img in images]

    ps = [imgToPoly(img, 0) for img in images]

    outlines = [polyToOutline(p) for p in ps]

    shadowVolume = shadowVolumeFromOutlines(outlines)
    
    return shadowVolume

def generateSTLFiles(imageFiles):
    # images = ["./input/u.png", "./input/v.png", "./input/a.png"]
    images = imageFiles
    images = [Image.open(fname) for fname in images]
    invert = True

    size = 32

    shadowVolume = shadowVolumeFromImages(images, size, invert, erode = False)
    scad_render_to_file(shadowVolume, "results/shadow.scad")

    eShadowVolume = shadowVolumeFromImages(images, size, invert, erode = True)
    scad_render_to_file(eShadowVolume, "results/eshadow.scad")

    # Invoke OpenSCAD to convert both of the above to STL
    p1 = subprocess.Popen(["./extern/openscad-2014.03/bin/openscad",
        "-o",
        "results/shadow.stl",
        "./results/shadow.scad"])

    p2 = subprocess.Popen(["./extern/openscad-2014.03/bin/openscad",
        "-o",
        "results/eshadow.stl",
        "./results/eshadow.scad"])

    print("Running OpenSCAD to generate initial STL models...")
    p1.wait()
    p2.wait()
    print("Done")

if __name__=="__main__":
    # generateSTLFiles(["./input/cat.png", "./input/dog.png"])

    s = scad_import(os.path.abspath("./results/shadow.stl"))
    es = scad_import(os.path.abspath("./results/eshadow.stl"))
    sOut = outlinesFromShadowVolume(s)
    esOut = outlinesFromShadowVolume(es)
    scad_render_to_file(linear_extrude(height=1, center=True, convexity=3)(sOut[0]), "./results/test.scad")
    # scad_render_to_file(difference()(s, es), "./results/test.scad")

