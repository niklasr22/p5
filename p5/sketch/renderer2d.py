#
# Part of p5: A Python package based on Processing
# Copyright (C) 2017-2019 Abhik Pal
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import numpy as np
import math
from ..pmath import matrix
from ..core import p5
from ..core.constants import SType
from ..core.primitives import Arc
from .shaders2d import src_default, src_fbuffer

import builtins

from vispy import gloo
from vispy.gloo import Program
from vispy.gloo import Texture2D
from vispy.gloo import VertexBuffer

from contextlib import contextmanager
from .shaders2d import src_texture
from .shaders2d import src_line
from .openglrenderer import OpenGLRenderer

from OpenGL.GLU import gluTessBeginPolygon, gluTessBeginContour, gluTessEndPolygon, gluTessEndContour, gluTessVertex


def _tess_new_contour(vertices):
	"""Given a list of vertices, evoke gluTess to create a contour
	"""
	gluTessBeginContour(p5.tess.tess)
	for v in vertices:
		gluTessVertex(p5.tess.tess, v, v)
	gluTessEndContour(p5.tess.tess)


def _vertices_to_render_primitive(gl_name, vertices):
	"""Returns a render primitive of gl_type with vertices in sequential order
	"""
	return [gl_name, np.asarray(vertices), np.arange(len(vertices), dtype=np.uint32)]


def _get_line_from_verts(vertices):
	"""Given a list of vertices, chain them sequentially in a line rendering primitive
	"""
	return ['lines', np.asarray(vertices), [np.arange(len(vertices))]]


def _get_line_from_indices(vertices, start, end):
	"""Given two columns of indices that represent edges, return a line rendering primitive

	:param vertices: List of vertices
	:type vertices: list

	:param start: Array of start positions of edges in vertex indices
	:type start: np.ndarray

	:param end: Array of end positions fo edges in vertex indices
	:type end: np.ndarray
	"""
	return ['lines', np.asarray(vertices),
			np.hstack((np.vstack(start), np.vstack(end)))]


def _add_edges_to_primitive_list(primitive_list, vertices, start, end):
	"""Adds edges to a list of render primitives, given their start and end positions (in vertex indices)

	:param start: Array of start positions of edges in vertex indices
	:type start: np.ndarray

	:param end: Array of end positions fo edges in vertex indices
	:type end: np.ndarray
	"""
	primitive_list.append(_get_line_from_indices(vertices, start, end))


def _not_enough_vertices(shape, n):
	"""Returns an error string that describes how many vertices are needed
	"""
	return "Need at least {} vertices for {}".format(n, shape)


def _wrong_multiple(shape, n):
	"""Returns an error string that describes the # of vertices is not a multiple of n
	"""
	return "{} requires the number of vertices to be a multiple of {}".format(shape.shape_type, n)


def _check_shape(shape):
	"""Checks if the shape is valid using assertions
	"""
	n_vert = len(shape.vertices)
	if shape.shape_type in [SType.TRIANGLES, SType.TRIANGLE_FAN, SType.TRIANGLE_STRIP]:
		assert n_vert >= 3, _not_enough_vertices(shape, 3)
	elif shape.shape_type in [SType.LINES, SType.LINE_STRIP]:
		assert n_vert >= 2, _not_enough_vertices(shape, 2)
	elif shape.shape_type in [SType.QUADS, SType.QUAD_STRIP]:
		assert n_vert >= 4, _not_enough_vertices(shape, 4)

	if shape.shape_type == SType.TRIANGLES:
		assert n_vert % 3 == 0, _wrong_multiple(shape, 3)
	if shape.shape_type == SType.QUADS:
		assert n_vert % 4 == 0, _wrong_multiple(shape, 4)

def _get_borders(shape):
	"""Generates the render primitives for the borders of a given shape

	:returns: ['lines', vertices, idx]
	"""
	render_primitives = []
	n_vert = len(shape.vertices)
	if shape.shape_type == SType.TRIANGLES:
		start = np.arange(n_vert)
		end = np.arange(n_vert) + np.tile([1, 1, -2], n_vert // 3)
		_add_edges_to_primitive_list(render_primitives, shape.vertices, start, end)
	elif shape.shape_type == SType.TRIANGLE_STRIP:
		start = np.concatenate((np.arange(n_vert - 1), np.arange(n_vert - 2)))
		end = np.concatenate((np.arange(1, n_vert), np.arange(2, n_vert)))
		_add_edges_to_primitive_list(render_primitives, shape.vertices, start, end)
	elif shape.shape_type == SType.TRIANGLE_FAN:
		start = np.concatenate((np.repeat([0], n_vert - 1), np.arange(1, n_vert - 1)))
		end = np.concatenate((np.arange(1, n_vert), np.arange(2, n_vert)))
		_add_edges_to_primitive_list(render_primitives, shape.vertices, start, end)
	elif shape.shape_type == SType.QUADS:
		start = np.arange(n_vert)
		end = np.arange(n_vert) + np.tile([1, 1, 1, -3], n_vert // 4)
		_add_edges_to_primitive_list(render_primitives, shape.vertices, start, end)
	elif shape.shape_type == SType.QUAD_STRIP:
		start = np.concatenate((np.arange(0, n_vert, 2), np.arange(n_vert - 2)))
		end = np.concatenate((np.arange(1, n_vert, 2), np.arange(2, n_vert)))
		_add_edges_to_primitive_list(render_primitives, shape.vertices, start, end)
	elif shape.shape_type == SType.LINES:
		start = np.arange(0, n_vert, 2)
		end = np.arange(1, n_vert, 2)
		_add_edges_to_primitive_list(render_primitives, shape.vertices, start, end)
	elif shape.shape_type == SType.LINE_STRIP:
		render_primitives.append(_get_line_from_verts(shape.vertices))
	elif shape.shape_type == SType.TESS:
		render_primitives.append(_get_line_from_verts(shape.vertices))
		for contour in shape.contours:
			render_primitives.append(_get_line_from_verts(contour))
	return render_primitives


def _get_meshes(shape):
	"""Generates the rendering primitives for the meshes of a given shape

	:returns: [shape_type, vertices, idx]
	"""
	render_primitives = []
	n_vert = len(shape.vertices)
	if shape.shape_type in [SType.TRIANGLES, SType.TRIANGLE_STRIP, SType.TRIANGLE_FAN, SType.QUAD_STRIP]:
		gl_name = shape.shape_type.name.lower()
		if gl_name == 'quad_strip':  # vispy does not support quad_strip
			gl_name = 'triangle_strip'  # but it can be drawn using triangle_strip
		render_primitives.append(_vertices_to_render_primitive(gl_name, shape.vertices))
	elif shape.shape_type == SType.QUADS:
		n_quad = len(shape.vertices) // 4
		render_primitives.append(['triangles', np.asarray(shape.vertices),
					   np.repeat(np.arange(0, n_vert, 4, dtype=np.uint32), 6) +
					   np.tile(np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32), n_quad)])
	elif shape.shape_type == SType.TESS:
		gluTessBeginPolygon(p5.tess.tess, None)
		_tess_new_contour(shape.vertices)
		if len(shape.contours) > 0:
			for contour in shape.contours:
				_tess_new_contour(contour)
		gluTessEndPolygon(p5.tess.tess)
		render_primitives += p5.tess.get_result()
	return render_primitives


def get_render_primitives(shape):
	"""Given a shape, return a list of render primitives in the form of [type, vertices, indices]
	"""
	_check_shape(shape)
	render_primitives = []
	if isinstance(shape, Arc):
		# Render meshes
		if p5.renderer.fill_enabled:
			render_primitives.extend(_get_meshes(shape))
		# Render borders
		if p5.renderer.stroke_enabled:
			if shape.arc_mode in ['CHORD', 'OPEN']:  # Implies shape.shape_type == TESS
				render_primitives.extend(_get_borders(shape))
			elif shape.arc_mode is None:             # Implies shape.shape_type == TRIANGLE_FAN
				render_primitives.append(_get_line_from_verts(shape.vertices[1:]))
			elif shape.arc_mode == 'PIE':            # Implies shape.shape_type == TRIANGLE_FAN
				render_primitives.append(_get_line_from_verts(shape.vertices))
	else:
		# Render points
		if shape.shape_type == SType.POINTS:
			render_primitives.append(_vertices_to_render_primitive(render_primitives, 'points'))
		# Render meshes
		if p5.renderer.fill_enabled:
			render_primitives.extend(_get_meshes(shape))
		# Render borders
		if p5.renderer.stroke_enabled:
			render_primitives.extend(_get_borders(shape))
	return render_primitives

class Renderer2D(OpenGLRenderer):
	def __init__(self):
		super().__init__(src_fbuffer, src_default)
		self.texture_prog = None
		self.line_prog = None
		self.modelview_matrix = np.identity(4)

	def initialize_renderer(self):
		super().initialize_renderer()
		self.texture_prog = Program(src_texture.vert, src_texture.frag)
		self.texture_prog['texcoord'] = self.fbuf_texcoords
		self.reset_view()

	def reset_view(self):
		self.viewport = (
			0,
			0,
			int(builtins.width * builtins.pixel_x_density),
			int(builtins.height * builtins.pixel_y_density),
		)
		self.texture_viewport = (
			0,
			0,
			builtins.width,
			builtins.height,
		)

		gloo.set_viewport(*self.viewport)

		cz = (builtins.height / 2) / math.tan(math.radians(30))
		self.projection_matrix = matrix.perspective_matrix(
			math.radians(60),
			builtins.width / builtins.height,
			0.1 * cz,
			10 * cz
		)
		self.modelview_matrix = matrix.translation_matrix(-builtins.width / 2, \
													 builtins.height / 2, \
													 -cz)
		self.modelview_matrix = self.modelview_matrix.dot(matrix.scale_transform(1, -1, 1))

		self.transform_matrix = np.identity(4)

		self.default_prog['modelview'] = self.modelview_matrix.T.flatten()
		self.default_prog['projection'] = self.projection_matrix.T.flatten()

		self.texture_prog['modelview'] = self.modelview_matrix.T.flatten()
		self.texture_prog['projection'] = self.projection_matrix.T.flatten()

		self.line_prog = Program(src_line.vert, src_line.frag)

		self.line_prog['modelview'] = self.modelview_matrix.T.flatten()
		self.line_prog['projection'] = self.projection_matrix.T.flatten()
		self.line_prog["height"] = builtins.height

		self.fbuffer_tex_front = Texture2D((builtins.height, builtins.width, 3))
		self.fbuffer_tex_back = Texture2D((builtins.height, builtins.width, 3))

		for buf in [self.fbuffer_tex_front, self.fbuffer_tex_back]:
			self.fbuffer.color_buffer = buf
			with self.fbuffer:
				self.clear()

	def clear(self, color=True, depth=True):
		"""Clear the renderer background."""
		gloo.set_state(clear_color=self.background_color)
		gloo.clear(color=color, depth=depth)

	def _comm_toggles(self, state=True):
		gloo.set_state(blend=state)
		gloo.set_state(depth_test=state)

		if state:
			gloo.set_state(blend_func=('src_alpha', 'one_minus_src_alpha'))
			gloo.set_state(depth_func='lequal')

	@contextmanager
	def draw_loop(self):
		"""The main draw loop context manager.
		"""

		self.transform_matrix = np.identity(4)

		self.default_prog['modelview'] = self.modelview_matrix.T.flatten()
		self.default_prog['projection'] = self.projection_matrix.T.flatten()

		self.fbuffer.color_buffer = self.fbuffer_tex_back

		with self.fbuffer:
			gloo.set_viewport(*self.texture_viewport)
			self._comm_toggles()
			self.fbuffer_prog['texture'] = self.fbuffer_tex_front
			self.fbuffer_prog.draw('triangle_strip')

			yield

			self.flush_geometry()
			self.transform_matrix = np.identity(4)

		gloo.set_viewport(*self.viewport)
		self._comm_toggles(False)
		self.clear()
		self.fbuffer_prog['texture'] = self.fbuffer_tex_back
		self.fbuffer_prog.draw('triangle_strip')

		self.fbuffer_tex_front, self.fbuffer_tex_back = self.fbuffer_tex_back, self.fbuffer_tex_front

	def _add_to_draw_queue(self, stype, vertices, idx, fill, stroke, stroke_weight, stroke_cap, stroke_join):
		"""Adds shape of stype to draw queue
		"""
		if stype == 'lines':
			self.draw_queue.append((stype, (vertices, idx, stroke, stroke_weight, stroke_cap, stroke_join)))
		else:
			self.draw_queue.append((stype, (vertices, idx, fill)))

	def render(self, shape):
		fill = shape.fill.normalized if shape.fill else None
		stroke = shape.stroke.normalized if shape.stroke else None
		stroke_weight = shape.stroke_weight
		stroke_cap = shape.stroke_cap
		stroke_join = shape.stroke_join

		obj_list = get_render_primitives(shape)
		for obj in obj_list:
			stype, vertices, idx = obj
			# Transform vertices
			vertices = self._transform_vertices(
				np.hstack([vertices, np.ones((len(vertices), 1))]),
				shape._matrix,
				self.transform_matrix)
			# Add to draw queue
			self._add_to_draw_queue(stype, vertices, idx, fill, stroke, stroke_weight, stroke_cap, stroke_join)

	def flush_geometry(self):
		"""Flush all the shape geometry from the draw queue to the GPU.
		"""
		current_queue = []
		for index, shape in enumerate(self.draw_queue):
			current_shape = self.draw_queue[index][0]
			current_queue.append(self.draw_queue[index][1])

			if current_shape == "lines":
				self.render_line(current_queue)
			else:
				self.render_default(current_shape, current_queue)

			current_queue = []

		self.draw_queue = []

	def render_line(self, queue):
		'''
		This rendering algorithm works by tesselating the line into
		multiple triangles.

		Reference: https://blog.mapbox.com/drawing-antialiased-lines-with-opengl-8766f34192dc
		'''

		if len(queue) == 0:
			return

		pos = []
		posPrev = []
		posCurr = []
		posNext = []
		markers = []
		side = []

		linewidth = []
		join_type = []
		cap_type = []
		color = []

		for line in queue:
			if len(line[1]) == 0:
				continue

			for segment in line[1]:
				for i in range(len(segment) - 1): # the data is sent to renderer in line segments
					for j in [0, 0, 1, 0, 1, 1]: # all the vertices of triangles
						if i + j - 1 >= 0:
							posPrev.append(line[0][segment[i + j - 1]])
						else:
							posPrev.append(line[0][segment[i + j]])

						if i + j + 1 < len(segment):
							posNext.append(line[0][segment[i + j + 1]])
						else:
							posNext.append(line[0][segment[i + j]])

						posCurr.append(line[0][segment[i + j]])

					markers.extend([1.0, -1.0, -1.0, -1.0, 1.0, -1.0]) # Is the vertex up/below the line segment
					side.extend([1.0, 1.0, -1.0, 1.0, -1.0, -1.0]) # Left or right side of the segment
					pos.extend([line[0][segment[i]]]*6) # Left vertex of each segment
					linewidth.extend([line[3]]*6)
					join_type.extend([line[5]]*6)
					cap_type.extend([line[4]]*6)
					color.extend([line[2]]*6)

		if len(pos) == 0:
			return

		posPrev = np.array(posPrev, np.float32)
		posCurr = np.array(posCurr, np.float32)
		posNext = np.array(posNext, np.float32)
		markers = np.array(markers, np.float32)
		side = np.array(side, np.float32)
		pos = np.array(pos, np.float32)
		linewidth = np.array(linewidth, np.float32)
		join_type = np.array(join_type, np.float32)
		cap_type = np.array(cap_type, np.float32)
		color = np.array(color, np.float32)

		self.line_prog['pos'] = gloo.VertexBuffer(pos)
		self.line_prog['posPrev'] = gloo.VertexBuffer(posPrev)
		self.line_prog['posCurr'] = gloo.VertexBuffer(posCurr)
		self.line_prog['posNext'] = gloo.VertexBuffer(posNext)
		self.line_prog['marker'] = gloo.VertexBuffer(markers)
		self.line_prog['side'] = gloo.VertexBuffer(side)
		self.line_prog['linewidth'] = gloo.VertexBuffer(linewidth)
		self.line_prog['join_type'] = gloo.VertexBuffer(join_type)
		self.line_prog['cap_type'] = gloo.VertexBuffer(cap_type)
		self.line_prog["color"] = gloo.VertexBuffer(color)

		self.line_prog.draw('triangles')

	def render_image(self, image, location, size):
		"""Render the image.

		:param image: image to be rendered
		:type image: builtins.Image

		:param location: top-left corner of the image
		:type location: tuple | list | builtins.Vector

		:param size: target size of the image to draw.
		:type size: tuple | list | builtins.Vector
		"""
		self.flush_geometry()

		self.texture_prog['fill_color'] = self.tint_color if self.tint_enabled else self.COLOR_WHITE
		self.texture_prog['transform'] = self.transform_matrix.T.flatten()

		x, y = location
		sx, sy = size
		imx, imy = image.size
		data = np.zeros(4,
						dtype=[('position', np.float32, 2),
							   ('texcoord', np.float32, 2)])
		data['texcoord'] = np.array([[0.0, 1.0],
									 [1.0, 1.0],
									 [0.0, 0.0],
									 [1.0, 0.0]],
									dtype=np.float32)
		data['position'] = np.array([[x, y + sy],
									 [x + sx, y + sy],
									 [x, y],
									 [x + sx, y]],
									dtype=np.float32)

		self.texture_prog['texture'] = image._texture
		self.texture_prog.bind(VertexBuffer(data))
		self.texture_prog.draw('triangle_strip')

	def cleanup(self):
		"""Run the clean-up routine for the renderer.

		This method is called when all drawing has been completed and the
		program is about to exit.

		"""
		OpenGLRenderer.cleanup(self)
		self.line_prog.delete()

