#define __USE_GNU 1
#include "include/ceph_fs.h"
#include "kernel/ioctl.h"

#include <fcntl.h>
#include <linux/types.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>


main()
{
    struct ceph_file_layout l;
    int fd = open("foo.txt", O_RDONLY);
    int r = ioctl(fd, CEPH_IOC_GET_LAYOUT, &l, sizeof(l));
    printf("get = %d\n", r);

    l.fl_stripe_unit = 65536;
    l.fl_object_size = 65536;

    r = ioctl(fd, CEPH_IOC_SET_LAYOUT, &l, sizeof(l));
    printf("set = %d\n", r);
}
