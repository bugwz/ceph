#include "auth/Crypto.h"
#include "common/ceph_crypto.h"
#include "common/code_environment.h"
#include "global/global_context.h"
#include "global/global_init.h"
#include "include/msgr.h"
#include "include/types.h"

#include "gtest/gtest.h"
#include <errno.h>
#include <pthread.h>
#include <time.h>
#include <unistd.h>
#include <vector>

// TODO: ensure OpenSSL init

int main(int argc, char** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
