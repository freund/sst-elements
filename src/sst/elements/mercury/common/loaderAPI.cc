// Copyright 2009-2025 NTESS. Under the terms
// of Contract DE-NA0003525 with NTESS, the U.S.
// Government retains certain rights in this software.
//
// Copyright (c) 2009-2025, NTESS
// All rights reserved.
//
// Portions are copyright of other developers:
// See the file CONTRIBUTORS.TXT in the top level directory
// of the distribution for more information.
//
// This file is part of the SST software package. For license
// information, see the LICENSE file in the top level directory of the
// distribution.

#include <sst/core/subcomponent.h>
#include <mercury/common/loaderAPI.h>

namespace SST {
namespace Hg {

loaderAPI::loaderAPI(SST::ComponentId_t id, SST::Params& params) : SST::SubComponent(id) { }
loaderAPI::~loaderAPI() { }

} // end namespace Hg
} // end namespace SST
