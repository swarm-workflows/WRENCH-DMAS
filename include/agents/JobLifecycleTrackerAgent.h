#ifndef JOB_LIFECYCLE_TRACKER_AGENT_H
#define JOB_LIFECYCLE_TRACKER_AGENT_H

#include "info/JobLifecycle.h"
#include <wrench-dev.h>

namespace wrench {

class JobLifecycleTrackerAgent : public ExecutionController {
  std::string job_list_;
  std::shared_ptr<std::vector<std::shared_ptr<JobLifecycle>>> job_lifecycles_;
  int num_completed_jobs_ = 0;
  int num_rejected_jobs_  = 0;
  int num_failed_jobs_    = 0;

  int main() override;
  void processEventCustom(const std::shared_ptr<CustomEvent>& event) override;

public:
  // Constructor
  JobLifecycleTrackerAgent(const std::string& hostname, const std::string& job_list)
      : ExecutionController(hostname, "job_lifecycle_tracker_agent"), job_list_(job_list)
  {
  }
};

} // namespace wrench
#endif // JOB_LIFECYCLE_TRACKER_AGENT_HPP
