#ifndef JOB_SCHEDULING_AGENT_H
#define JOB_SCHEDULING_AGENT_H

#include <memory>
#include <wrench-dev.h>

#include "info/HPCSystemDescription.h"
#include "info/JobDescription.h"
#include "policies/SchedulingPolicy.h"

namespace wrench {

class JobLifecycleTrackerAgent;

/**
 *  @brief An execution controller implementation
 */
class JobSchedulingAgent : public ExecutionController {
  std::shared_ptr<HPCSystemDescription> hpc_system_description_;
  std::shared_ptr<SchedulingPolicy> scheduling_policy_;
  std::shared_ptr<JobManager> job_manager_;

  std::shared_ptr<BatchComputeService> batch_compute_service_;
  std::shared_ptr<JobLifecycleTrackerAgent> tracker_;

  std::unordered_map<int, std::map<std::shared_ptr<JobSchedulingAgent>, std::pair<double, double>>> all_bids_;

  int main() override;
  void processEventCustom(const std::shared_ptr<CustomEvent>& event) override;
  void processEventCompoundJobCompletion(const std::shared_ptr<CompoundJobCompletedEvent>& event) override;
  void processEventCompoundJobFailure(const std::shared_ptr<CompoundJobFailedEvent>& event) override;
  void processEventTimer(const std::shared_ptr<wrench::TimerEvent>& event) override;
  void build_and_submit_job(int job_id, const std::shared_ptr<JobDescription>& job_description);

public:
  JobSchedulingAgent(const std::string& hostname, const std::shared_ptr<HPCSystemDescription>& hpc_system_description,
                     const std::shared_ptr<SchedulingPolicy>& scheduling_policy,
                     const std::shared_ptr<BatchComputeService>& batch_compute_service)
      : ExecutionController(hostname, "job_scheduling_agent")
      , hpc_system_description_(hpc_system_description)
      , scheduling_policy_(scheduling_policy)
      , batch_compute_service_(batch_compute_service)
  {
  }

  void set_scheduling_policy_network(const std::vector<std::shared_ptr<wrench::JobSchedulingAgent>>& network)
  {
    scheduling_policy_->set_job_scheduling_agent_network(network);
  }
  const std::shared_ptr<HPCSystemDescription>& get_hpc_system_description() const { return hpc_system_description_; }

  const std::shared_ptr<BatchComputeService>& get_batch_compute_service() const { return batch_compute_service_; }

  void set_job_lifecycle_tracker(std::shared_ptr<JobLifecycleTrackerAgent> tracker) { tracker_ = tracker; }
  void mark_agent_as_failed(std::shared_ptr<JobSchedulingAgent> agent);
  const std::string& get_hpc_system_name() const { return hpc_system_description_->get_name(); }
};

} // namespace wrench
#endif // JOB_SCHEDULING_AGENT_H
