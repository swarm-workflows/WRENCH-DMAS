#ifndef WORKLOAD_CENTRALIZED_SUBMISSION_AGENT_H
#define WORKLOAD_CENTRALIZED_SUBMISSION_AGENT_H

#include "policies/CentralizedSchedulingPolicy.h"
#include <wrench-dev.h>

namespace wrench {

class JobLifecycleTrackerAgent;
class JobSchedulingAgent;

class WorkloadCentralizedSubmissionAgent : public ExecutionController {
  const std::string& job_list_;
  std::vector<std::shared_ptr<JobSchedulingAgent>> job_scheduling_agents_;
  std::shared_ptr<JobLifecycleTrackerAgent> tracker_;
  std::shared_ptr<CentralizedSchedulingPolicy> scheduling_policy_;

  int main() override;
  void processEventCustom(const std::shared_ptr<CustomEvent>& event) override { /* no-op*/ };

public:
  // Constructor
  WorkloadCentralizedSubmissionAgent(const std::string& hostname, const std::string& job_list,
                                     const std::vector<std::shared_ptr<JobSchedulingAgent>>& job_scheduling_agents,
                                     const std::shared_ptr<CentralizedSchedulingPolicy>& scheduling_policy)
      : ExecutionController(hostname, "workload_centralized_submission_agent")
      , job_list_(job_list)
      , job_scheduling_agents_(job_scheduling_agents)
      , scheduling_policy_(scheduling_policy)
  {
  }

  void set_job_lifecycle_tracker(std::shared_ptr<JobLifecycleTrackerAgent> tracker) { tracker_ = tracker; }
};

} // namespace wrench
#endif // WORKLOAD_CENTRALIZED_SUBMISSION_AGENT_H
