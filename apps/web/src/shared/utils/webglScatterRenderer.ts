export interface ScatterViewport {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export interface ScatterPixelRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export type ScatterColor = readonly [number, number, number, number];
export type ScatterPointId = string | number;

export interface WebGLScatterRendererOptions {
  pointColor?: ScatterColor;
  selectedColor?: ScatterColor;
  boundaryColor?: ScatterColor;
  backgroundColor?: ScatterColor;
  pointSize?: number;
  selectedPointSize?: number;
  gridPaddingPx?: number;
  preserveAspectRatio?: boolean;
}

const POINT_VERTEX_SHADER = `
attribute vec2 a_position;

uniform vec4 u_viewport;
uniform vec4 u_pixel_rect;
uniform vec2 u_canvas_size;
uniform float u_point_size;
uniform float u_dpr;

void main() {
  vec2 denom = vec2(
    max(abs(u_viewport.y - u_viewport.x), 0.000001),
    max(abs(u_viewport.w - u_viewport.z), 0.000001)
  );
  vec2 normalized = (a_position - vec2(u_viewport.x, u_viewport.z)) / denom;
  vec2 pixel = vec2(
    u_pixel_rect.x + normalized.x * u_pixel_rect.z,
    u_pixel_rect.y + (1.0 - normalized.y) * u_pixel_rect.w
  );
  vec2 clip = vec2(
    pixel.x / u_canvas_size.x * 2.0 - 1.0,
    1.0 - pixel.y / u_canvas_size.y * 2.0
  );
  gl_Position = vec4(clip, 0.0, 1.0);
  gl_PointSize = u_point_size * u_dpr;
}
`;

const POINT_FRAGMENT_SHADER = `
precision mediump float;

uniform vec4 u_color;

void main() {
  float dist = distance(gl_PointCoord, vec2(0.5, 0.5)) * 2.0;
  float alpha = 1.0 - smoothstep(0.72, 1.0, dist);
  if (alpha <= 0.0) discard;
  gl_FragColor = vec4(u_color.rgb, u_color.a * alpha);
}
`;

const LINE_VERTEX_SHADER = `
attribute vec2 a_position;

uniform vec4 u_viewport;
uniform vec4 u_pixel_rect;
uniform vec2 u_canvas_size;

void main() {
  vec2 denom = vec2(
    max(abs(u_viewport.y - u_viewport.x), 0.000001),
    max(abs(u_viewport.w - u_viewport.z), 0.000001)
  );
  vec2 normalized = (a_position - vec2(u_viewport.x, u_viewport.z)) / denom;
  vec2 pixel = vec2(
    u_pixel_rect.x + normalized.x * u_pixel_rect.z,
    u_pixel_rect.y + (1.0 - normalized.y) * u_pixel_rect.w
  );
  vec2 clip = vec2(
    pixel.x / u_canvas_size.x * 2.0 - 1.0,
    1.0 - pixel.y / u_canvas_size.y * 2.0
  );
  gl_Position = vec4(clip, 0.0, 1.0);
}
`;

const LINE_FRAGMENT_SHADER = `
precision mediump float;

uniform vec4 u_color;

void main() {
  gl_FragColor = u_color;
}
`;

function createShader(
  gl: WebGLRenderingContext,
  type: number,
  source: string,
): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("Failed to create WebGL shader");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const message = gl.getShaderInfoLog(shader) ?? "unknown shader compile error";
    gl.deleteShader(shader);
    throw new Error(message);
  }
  return shader;
}

function createProgram(
  gl: WebGLRenderingContext,
  vertexSource: string,
  fragmentSource: string,
): WebGLProgram {
  const program = gl.createProgram();
  if (!program) throw new Error("Failed to create WebGL program");

  const vertex = createShader(gl, gl.VERTEX_SHADER, vertexSource);
  const fragment = createShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const message = gl.getProgramInfoLog(program) ?? "unknown program link error";
    gl.deleteProgram(program);
    throw new Error(message);
  }
  return program;
}

function requireUniform(
  gl: WebGLRenderingContext,
  program: WebGLProgram,
  name: string,
): WebGLUniformLocation {
  const location = gl.getUniformLocation(program, name);
  if (!location) throw new Error(`Missing WebGL uniform: ${name}`);
  return location;
}

export class WebGLScatterRenderer {
  readonly canvas: HTMLCanvasElement;

  private readonly gl: WebGLRenderingContext;
  private readonly pointProgram: WebGLProgram;
  private readonly lineProgram: WebGLProgram;
  private readonly pointPositionLocation: number;
  private readonly linePositionLocation: number;
  private readonly pointBuffer: WebGLBuffer;
  private readonly selectedBuffer: WebGLBuffer;
  private readonly boundaryBuffer: WebGLBuffer;
  private readonly pointUniforms: {
    viewport: WebGLUniformLocation;
    pixelRect: WebGLUniformLocation;
    canvasSize: WebGLUniformLocation;
    pointSize: WebGLUniformLocation;
    dpr: WebGLUniformLocation;
    color: WebGLUniformLocation;
  };
  private readonly lineUniforms: {
    viewport: WebGLUniformLocation;
    pixelRect: WebGLUniformLocation;
    canvasSize: WebGLUniformLocation;
    color: WebGLUniformLocation;
  };
  private readonly options: Required<WebGLScatterRendererOptions>;

  private viewport: ScatterViewport = { minX: 0, maxX: 1, minY: 0, maxY: 1 };
  private pointsCount = 0;
  private selectedCount = 0;
  private boundaryCount = 0;
  private disposed = false;
  private dpr = 1;
  private cssWidth = 1;
  private cssHeight = 1;

  pixelRect: ScatterPixelRect = { left: 0, top: 0, width: 1, height: 1 };

  constructor(canvas: HTMLCanvasElement, options: WebGLScatterRendererOptions = {}) {
    this.canvas = canvas;
    this.options = {
      pointColor: options.pointColor ?? [0.847, 0.227, 0.227, 1],
      selectedColor: options.selectedColor ?? [0.969, 0.788, 0.282, 1],
      boundaryColor: options.boundaryColor ?? [0, 0, 0, 1],
      backgroundColor: options.backgroundColor ?? [1, 1, 1, 1],
      pointSize: options.pointSize ?? 1,
      selectedPointSize: options.selectedPointSize ?? 4,
      gridPaddingPx: options.gridPaddingPx ?? 8,
      preserveAspectRatio: options.preserveAspectRatio ?? true,
    };

    const gl = canvas.getContext("webgl", {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      preserveDrawingBuffer: false,
    });
    if (!gl) throw new Error("WebGL is not available");

    this.gl = gl;
    this.pointProgram = createProgram(gl, POINT_VERTEX_SHADER, POINT_FRAGMENT_SHADER);
    this.lineProgram = createProgram(gl, LINE_VERTEX_SHADER, LINE_FRAGMENT_SHADER);
    this.pointPositionLocation = gl.getAttribLocation(this.pointProgram, "a_position");
    this.linePositionLocation = gl.getAttribLocation(this.lineProgram, "a_position");
    this.pointUniforms = {
      viewport: requireUniform(gl, this.pointProgram, "u_viewport"),
      pixelRect: requireUniform(gl, this.pointProgram, "u_pixel_rect"),
      canvasSize: requireUniform(gl, this.pointProgram, "u_canvas_size"),
      pointSize: requireUniform(gl, this.pointProgram, "u_point_size"),
      dpr: requireUniform(gl, this.pointProgram, "u_dpr"),
      color: requireUniform(gl, this.pointProgram, "u_color"),
    };
    this.lineUniforms = {
      viewport: requireUniform(gl, this.lineProgram, "u_viewport"),
      pixelRect: requireUniform(gl, this.lineProgram, "u_pixel_rect"),
      canvasSize: requireUniform(gl, this.lineProgram, "u_canvas_size"),
      color: requireUniform(gl, this.lineProgram, "u_color"),
    };

    const pointBuffer = gl.createBuffer();
    const selectedBuffer = gl.createBuffer();
    const boundaryBuffer = gl.createBuffer();
    if (!pointBuffer || !selectedBuffer || !boundaryBuffer) {
      throw new Error("Failed to allocate WebGL buffers");
    }
    this.pointBuffer = pointBuffer;
    this.selectedBuffer = selectedBuffer;
    this.boundaryBuffer = boundaryBuffer;

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  }

  setViewport(viewport: ScatterViewport): void {
    this.viewport = viewport;
  }

  setPoints(points: ArrayLike<number>): void {
    const count = Math.floor(points.length / 3);
    const positions = new Float32Array(count * 2);
    for (let source = 0, target = 0; source + 1 < points.length; source += 3, target += 2) {
      positions[target] = points[source];
      positions[target + 1] = points[source + 1];
    }

    this.pointsCount = count;
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.pointBuffer);
    this.gl.bufferData(this.gl.ARRAY_BUFFER, positions, this.gl.STATIC_DRAW);
  }

  setSelectedPoints(points: ArrayLike<number>, selectedIds: ReadonlySet<ScatterPointId>): void {
    if (selectedIds.size === 0) {
      this.selectedCount = 0;
      this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.selectedBuffer);
      this.gl.bufferData(this.gl.ARRAY_BUFFER, 0, this.gl.DYNAMIC_DRAW);
      return;
    }

    const selected: number[] = [];
    for (let i = 0; i + 2 < points.length; i += 3) {
      const id = points[i + 2];
      if (selectedIds.has(id) || selectedIds.has(String(id))) {
        selected.push(points[i], points[i + 1]);
      }
    }

    this.selectedCount = selected.length / 2;
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.selectedBuffer);
    this.gl.bufferData(this.gl.ARRAY_BUFFER, new Float32Array(selected), this.gl.DYNAMIC_DRAW);
  }

  setBoundaryCircle(radius: number, segments = 180): void {
    const vertices = new Float32Array(segments * 2);
    for (let i = 0; i < segments; i += 1) {
      const theta = (Math.PI * 2 * i) / segments;
      vertices[i * 2] = radius * Math.cos(theta);
      vertices[i * 2 + 1] = radius * Math.sin(theta);
    }
    this.boundaryCount = segments;
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.boundaryBuffer);
    this.gl.bufferData(this.gl.ARRAY_BUFFER, vertices, this.gl.STATIC_DRAW);
  }

  clearBoundary(): void {
    this.boundaryCount = 0;
  }

  screenToData(localX: number, localY: number): [number, number] | null {
    const rect = this.pixelRect;
    const pixelX = localX - rect.left;
    const pixelY = localY - rect.top;
    if (pixelX < 0 || pixelX > rect.width || pixelY < 0 || pixelY > rect.height) {
      return null;
    }

    const fracX = pixelX / Math.max(1, rect.width);
    const fracY = 1 - pixelY / Math.max(1, rect.height);
    return [
      this.viewport.minX + fracX * (this.viewport.maxX - this.viewport.minX),
      this.viewport.minY + fracY * (this.viewport.maxY - this.viewport.minY),
    ];
  }

  render(): void {
    if (this.disposed) return;

    const gl = this.gl;
    this.resizeCanvas();
    this.updatePixelRect();

    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.disable(gl.SCISSOR_TEST);
    gl.clearColor(...this.options.backgroundColor);
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.enable(gl.SCISSOR_TEST);
    gl.scissor(
      Math.floor(this.pixelRect.left * this.dpr),
      Math.floor((this.cssHeight - this.pixelRect.top - this.pixelRect.height) * this.dpr),
      Math.max(1, Math.floor(this.pixelRect.width * this.dpr)),
      Math.max(1, Math.floor(this.pixelRect.height * this.dpr)),
    );

    if (this.pointsCount > 0) {
      this.drawPoints(this.pointBuffer, this.pointsCount, this.options.pointSize, this.options.pointColor);
    }
    if (this.selectedCount > 0) {
      this.drawPoints(
        this.selectedBuffer,
        this.selectedCount,
        this.options.selectedPointSize,
        this.options.selectedColor,
      );
    }
    if (this.boundaryCount > 0) {
      this.drawBoundary();
    }
    gl.disable(gl.SCISSOR_TEST);
  }

  destroy(): void {
    if (this.disposed) return;
    this.disposed = true;
    const gl = this.gl;
    gl.deleteProgram(this.pointProgram);
    gl.deleteProgram(this.lineProgram);
    gl.deleteBuffer(this.pointBuffer);
    gl.deleteBuffer(this.selectedBuffer);
    gl.deleteBuffer(this.boundaryBuffer);
  }

  private resizeCanvas(): void {
    this.dpr = window.devicePixelRatio || 1;
    this.cssWidth = Math.max(1, this.canvas.clientWidth || this.canvas.parentElement?.clientWidth || 1);
    this.cssHeight = Math.max(1, this.canvas.clientHeight || this.canvas.parentElement?.clientHeight || 1);
    const width = Math.max(1, Math.floor(this.cssWidth * this.dpr));
    const height = Math.max(1, Math.floor(this.cssHeight * this.dpr));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
  }

  private updatePixelRect(): void {
    if (this.options.preserveAspectRatio) {
      const side = Math.max(1, Math.min(this.cssWidth, this.cssHeight) - this.options.gridPaddingPx * 2);
      this.pixelRect = {
        left: Math.max(0, (this.cssWidth - side) / 2),
        top: Math.max(0, (this.cssHeight - side) / 2),
        width: side,
        height: side,
      };
      return;
    }

    this.pixelRect = {
      left: this.options.gridPaddingPx,
      top: this.options.gridPaddingPx,
      width: Math.max(1, this.cssWidth - this.options.gridPaddingPx * 2),
      height: Math.max(1, this.cssHeight - this.options.gridPaddingPx * 2),
    };
  }

  private applyPointUniforms(pointSize: number, color: ScatterColor): void {
    const gl = this.gl;
    const { viewport, pixelRect, canvasSize, dpr, color: colorUniform, pointSize: size } = this.pointUniforms;
    gl.uniform4f(viewport, this.viewport.minX, this.viewport.maxX, this.viewport.minY, this.viewport.maxY);
    gl.uniform4f(pixelRect, this.pixelRect.left, this.pixelRect.top, this.pixelRect.width, this.pixelRect.height);
    gl.uniform2f(canvasSize, this.cssWidth, this.cssHeight);
    gl.uniform1f(size, pointSize);
    gl.uniform1f(dpr, this.dpr);
    gl.uniform4f(colorUniform, color[0], color[1], color[2], color[3]);
  }

  private drawPoints(
    buffer: WebGLBuffer,
    count: number,
    pointSize: number,
    color: ScatterColor,
  ): void {
    const gl = this.gl;
    gl.useProgram(this.pointProgram);
    this.applyPointUniforms(pointSize, color);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.enableVertexAttribArray(this.pointPositionLocation);
    gl.vertexAttribPointer(this.pointPositionLocation, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.POINTS, 0, count);
  }

  private drawBoundary(): void {
    const gl = this.gl;
    const { viewport, pixelRect, canvasSize, color } = this.lineUniforms;
    gl.useProgram(this.lineProgram);
    gl.uniform4f(viewport, this.viewport.minX, this.viewport.maxX, this.viewport.minY, this.viewport.maxY);
    gl.uniform4f(pixelRect, this.pixelRect.left, this.pixelRect.top, this.pixelRect.width, this.pixelRect.height);
    gl.uniform2f(canvasSize, this.cssWidth, this.cssHeight);
    gl.uniform4f(
      color,
      this.options.boundaryColor[0],
      this.options.boundaryColor[1],
      this.options.boundaryColor[2],
      this.options.boundaryColor[3],
    );
    gl.bindBuffer(gl.ARRAY_BUFFER, this.boundaryBuffer);
    gl.enableVertexAttribArray(this.linePositionLocation);
    gl.vertexAttribPointer(this.linePositionLocation, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.LINE_LOOP, 0, this.boundaryCount);
  }
}
