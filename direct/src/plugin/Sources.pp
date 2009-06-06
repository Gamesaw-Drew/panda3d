// This directory is still experimental.  Define HAVE_P3D_PLUGIN in
// your Config.pp to build it.
#define BUILD_DIRECTORY $[HAVE_P3D_PLUGIN]

#begin lib_target
  #define TARGET p3d_plugin

  #define COMBINED_SOURCES \
    $[TARGET]_composite1.cxx

  #define SOURCES \
    p3d_plugin.h \
    p3d_plugin_common.h \
    p3dInstance.h p3dInstance.I \
    p3dInstanceManager.h p3dInstanceManager.I \
    p3dPython.h p3dPython.I \
    p3dSession.h p3dSession.I

  #define INCLUDED_SOURCES \
    p3d_plugin.cxx \
    p3dInstance.cxx \
    p3dInstanceManager.cxx \
    p3dPython.cxx \
    p3dSession.cxx

  #define INSTALL_HEADERS \
    p3d_plugin.h

#end lib_target

#begin bin_target
  #define TARGET panda3d

  #define SOURCES \
    panda3d.cxx \
    $[if $[WINDOWS_PLATFORM],wingetopt.h wingetopt.c]

  #define WIN_SYS_LIBS user32.lib gdi32.lib

#end bin_target