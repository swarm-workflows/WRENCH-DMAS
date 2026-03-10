#ifndef CONTROLMESSAGES_H
#define CONTROLMESSAGES_H

#include "agents/JobSchedulingAgent.h"
#include "info/JobDescription.h"
#include <wrench-dev.h>

#define CONTROL_MESSAGE_SIZE 0      // Size in bytes
#define BROADCAST_MESSAGE_SIZE 1024 // Size in bytes

namespace wrench {

/// Message to send a job request to a job scheduling agent
class JobRequestMessage : public ExecutionControllerCustomEventMessage {
  std::shared_ptr<JobDescription> job_description_;
  bool can_forward_;
  bool skip_bidding_;

public:
  /// @brief
  /// @param job_description job description
  /// @param can_forward whether the job can be forwarded to another job scheduling agent
  /// @param skip_bidding whether to skip the bidding process (true when sent by centralized scheduler)
  JobRequestMessage(const std::shared_ptr<JobDescription>& job_description, bool can_forward, bool skip_bidding = false)
      : ExecutionControllerCustomEventMessage(can_forward ? CONTROL_MESSAGE_SIZE : BROADCAST_MESSAGE_SIZE)
      , job_description_(job_description)
      , can_forward_(can_forward)
      , skip_bidding_(skip_bidding)
  {
  }
  bool can_be_forwarded() const { return can_forward_; }
  bool should_skip_bidding() const { return skip_bidding_; }
  const std::shared_ptr<JobDescription>& get_job_description() const { return job_description_; }
};

/// Message to send a bid
class BidOnJobMessage : public ExecutionControllerCustomEventMessage {
  const std::shared_ptr<wrench::JobSchedulingAgent> bidder_;
  const std::shared_ptr<JobDescription> job_description_;
  double bid_;
  double tie_breaker_;

public:
  BidOnJobMessage(const std::shared_ptr<wrench::S4U_Daemon>& bidder,
                  const std::shared_ptr<JobDescription>& job_description, double bid, double tie_breaker)
      : ExecutionControllerCustomEventMessage(BROADCAST_MESSAGE_SIZE)
      , bidder_(std::static_pointer_cast<JobSchedulingAgent>(bidder))
      , job_description_(job_description)
      , bid_(bid)
      , tie_breaker_(tie_breaker)
  {
  }

  const std::shared_ptr<JobSchedulingAgent> get_bidder() const { return bidder_; }
  const std::shared_ptr<JobDescription> get_job_description() const { return job_description_; }
  double get_bid() const { return bid_; }
  double get_tie_breaker() const { return tie_breaker_; }
};

/// Message to send a job lifecycle event notification
enum class JobLifecycleEventType { SUBMISSION, SCHEDULING, REJECT, START, COMPLETION, FAIL };

class JobLifecycleTrackingMessage : public ExecutionControllerCustomEventMessage {
  int job_id_;
  double when_;
  std::string sent_from_;
  JobLifecycleEventType event_type_;
  std::string bids_;
  std::string failure_cause_;

public:
  JobLifecycleTrackingMessage(int job_id, const std::string& sender_name, double now, JobLifecycleEventType event_type,
                              const std::string& bids = "", const std::string& failure_cause = "")
      : ExecutionControllerCustomEventMessage(CONTROL_MESSAGE_SIZE)
      , job_id_(job_id)
      , sent_from_(sender_name)
      , when_(now)
      , event_type_(event_type)
      , bids_(bids)
      , failure_cause_(failure_cause)
  {
  }
  int get_job_id() const { return job_id_; }
  JobLifecycleEventType get_event_type() const { return event_type_; }
  double get_when() const { return when_; }
  const std::string& get_sender() const { return sent_from_; }
  const std::string& get_bids() const { return bids_; }
  const std::string& get_failure_cause() const { return failure_cause_; }
};

} // namespace wrench
#endif // CONTROLMESSAGES_H
