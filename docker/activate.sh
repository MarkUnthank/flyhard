# Source this in SSH sessions, which do not inherit the container environment.
source /opt/flyhard-env/bin/activate
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
export PYVISTA_OFF_SCREEN=true VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow
export PYTHONPATH=/workspace/flyhard/src
if [ -x /workspace/flyhard-runtime/blender-5.2.1/blender-5.2.1-linux-x64/blender ]; then
  export PATH=/workspace/flyhard-runtime/blender-5.2.1/blender-5.2.1-linux-x64:$PATH
fi
