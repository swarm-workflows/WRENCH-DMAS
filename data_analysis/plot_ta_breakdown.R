library(ggplot2)
library(plyr)
library(patchwork)

results_dir <- "../results"

files <- list.files(results_dir, pattern = "\\.csv$", full.names = TRUE)
files <- files[!grepl("aggregated_metrics", files)]

strategy_label <- function(bname) {
  if (grepl("EmbeddingBidding", bname)) return("Embedding")
  if (grepl("HeuristicBidding", bname)) return("Heuristic")
  if (grepl("LLMBidding",       bname)) return("LLM")
  if (grepl("PureLocal",        bname)) return("Pure Local")
  return(NA_character_)
}

workload_label <- function(bname) {
  if (grepl("small_short", bname)) return("Small/Short")
  if (grepl("large_long",  bname)) return("Large/Long")
  if (grepl("mixed",       bname)) return("Mixed")
  return(NA_character_)
}

arrival_label <- function(bname) {
  if (grepl("bursty_high", bname)) return("Bursty High")
  if (grepl("bursty_low",  bname)) return("Bursty Low")
  if (grepl("business",    bname)) return("Business")
  return(NA_character_)
}

strat_levels <- c("Heuristic", "Embedding", "LLM")

# Colors pinned to positions 2-4 of ggplot's 4-hue default palette,
# keeping them consistent with the turnaround boxplot (which uses all 4)
strat_colors <- c("Heuristic" = "#7CAE00",
                  "Embedding" = "#00BFC4",
                  "LLM"       = "#C77CFF")

# Per-scenario mean turnaround with both classifiers
scenario_data <- do.call(rbind, lapply(files, function(f) {
  bname <- sub("\\.csv$", "", basename(f))
  strat   <- strategy_label(bname)
  wtype   <- workload_label(bname)
  arrival <- arrival_label(bname)
  if (is.na(strat) || is.na(wtype) || is.na(arrival)) return(NULL)
  df <- read.csv(f, stringsAsFactors = FALSE)
  df <- df[df$FinalStatus == "COMPLETED", ]
  data.frame(Strategy    = strat,
             WorkloadType = wtype,
             Arrival      = arrival,
             MeanTA       = mean((df$EndTime - df$SubmissionTime) / 3600))
}))

# Summaries
scenario_data <- scenario_data[scenario_data$Strategy != "Pure Local", ]

ta_wtype <- ddply(scenario_data, c("Strategy", "WorkloadType"), summarise,
                  MeanTA = mean(MeanTA))
ta_arr   <- ddply(scenario_data, c("Strategy", "Arrival"),      summarise,
                  MeanTA = mean(MeanTA))

ta_wtype$Strategy     <- factor(ta_wtype$Strategy,     levels = strat_levels)
ta_wtype$WorkloadType <- factor(ta_wtype$WorkloadType,
                                levels = c("Small/Short", "Mixed", "Large/Long"))

ta_arr$Strategy <- factor(ta_arr$Strategy, levels = strat_levels)
ta_arr$Arrival  <- factor(ta_arr$Arrival,
                          levels = c("Business", "Bursty Low", "Bursty High"))

bar_args <- list(position = position_dodge(width = 0.72), width = 0.65, alpha = 0.85)

scale_manual <- list(
  scale_fill_manual(values  = strat_colors),
  scale_color_manual(values = strat_colors)
)

pC <- ggplot(ta_arr, aes(x = Arrival, y = MeanTA,
                          fill = Strategy, color = Strategy)) +
  do.call(geom_col, bar_args) +
  scale_manual +
  scale_y_continuous(name   = "Mean turnaround time (hours)",
                     limits = c(0, NA),
                     expand = expansion(mult = c(0, 0.04))) +
  labs(x = "Arrival pattern", fill = "Strategy", color = "Strategy") +
  theme_bw(base_size = 9) +
  theme(legend.position = "none")

pB <- ggplot(ta_wtype, aes(x = WorkloadType, y = MeanTA,
                            fill = Strategy, color = Strategy)) +
  do.call(geom_col, bar_args) +
  scale_manual +
  scale_y_continuous(name   = "Mean turnaround time (hours)",
                     limits = c(0, NA),
                     expand = expansion(mult = c(0, 0.04))) +
  labs(x = "Workload type", fill = "Strategy", color = "Strategy") +
  theme_bw(base_size = 9) +
  theme(legend.position = "none")

combined <- pC + pB +
  plot_layout(guides = "collect") &
  theme(legend.position  = "top",
        legend.title     = element_text(size = 8),
        legend.key.size  = unit(0.35, "cm"))

out <- "./ta_breakdown"
ggsave(paste0(out, ".pdf"), combined, width = 5.5, height = 2.8, device = "pdf")
ggsave(paste0(out, ".png"), combined, width = 5.5, height = 2.8, dpi = 300)
cat("Saved", out, "\n")
