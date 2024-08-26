# 设置安装排除项
# 这部分代码定义了一些在安装过程中需要排除的文件和目录模式。
# 例如，CMakeLists.txt、.gitignore、tox.ini、以requirements和constraints开头的.txt文件，
# 以及tests目录下的所有文件都将被排除在外。
set(mgr_module_install_excludes
  PATTERN "CMakeLists.txt" EXCLUDE
  PATTERN ".gitignore" EXCLUDE
  PATTERN "tox.ini" EXCLUDE
  PATTERN "requirements*.txt" EXCLUDE
  PATTERN "constraints*.txt" EXCLUDE
  PATTERN "tests/*" EXCLUDE)

# 添加子目录
# 这行代码表示将dashboard子目录添加到构建过程中。
add_subdirectory(dashboard)

# 条件添加子目录
if(WITH_MGR_ROOK_CLIENT)
  add_subdirectory(rook)
endif()
if(WITH_TESTS)
  include(AddCephTest)
  add_tox_test(mgr ${CMAKE_CURRENT_SOURCE_DIR} TOX_ENVS py3 py37 mypy flake8 jinjalint nooptional)
endif()

# Location needs to match default setting for mgr_module_path, currently:
# OPTION(mgr_module_path, OPT_STR, CEPH_INSTALL_DATADIR "/mgr")
# 位置需要与 mgr_module_path 的默认设置匹配，当前为：
# OPTION(mgr_module_path, OPT_STR, CEPH_INSTALL_DATADIR "/mgr")
# 这部分代码定义了一个名为 mgr_modules 的列表，包含多个模块名称，这些模块将被安装
# 到 mgr_module_path 指定的路径中。注释部分说明了路径需要与 mgr_module_path 的默认设置匹配。
set(mgr_modules
  alerts
  balancer
  cephadm
  crash
  # dashboard (optional)
  devicehealth
  diskprediction_local
  # hello is an example for developers, not for user
  influx
  insights
  iostat
  k8sevents
  localpool
  mds_autoscaler
  mirroring
  nfs
  orchestrator
  osd_perf_query
  osd_support
  pg_autoscaler
  progress
  prometheus
  rbd_support
  restful
  rgw
  # rook (optional)
  selftest
  snap_schedule
  stats
  status
  telegraf
  telemetry
  # tests (for testing purpose only)
  test_orchestrator
  volumes
  zabbix)

install(DIRECTORY ${mgr_modules}
  DESTINATION ${CEPH_INSTALL_DATADIR}/mgr
  ${mgr_module_install_excludes})
install(FILES mgr_module.py mgr_util.py object_format.py
  DESTINATION ${CEPH_INSTALL_DATADIR}/mgr)
