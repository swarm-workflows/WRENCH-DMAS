library(ggplot2)
library(plyr)

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

# One row per scenario: its mean turnaround in hours
data <- do.call(rbind, lapply(files, function(f) {
  bname <- sub("\\.csv$", "", basename(f))
  strat <- strategy_label(bname)
  if (is.na(strat)) return(NULL)
  df <- read.csv(f, stringsAsFactors = FALSE)
  df <- df[df$FinalStatus == "COMPLETED", ]
  data.frame(Strategy        = strat,
             MeanTurnaround  = mean((df$EndTime - df$SubmissionTime) / 3600))
}))

data$Strategy <- factor(data$Strategy,
  levels = c("Pure Local", "Heuristic", "Embedding", "LLM"))

p <- ggplot(data, aes(x = Strategy, y = MeanTurnaround, color = Strategy)) +
  geom_boxplot(width = 0.48) +
  stat_summary(fun = mean, geom = "point", shape = 17, size = 2.2) +
  scale_y_continuous(
    name   = "Turnaround time (hours)",
    limits = c(0, NA),
    expand = expansion(mult = c(0, 0.04))
  ) +
  labs(x = "Strategy") +
  theme_bw(base_size = 11) +
  theme(legend.position = "none")

out <- "./turnaround_boxplot"
ggsave(paste0(out, ".pdf"), p, width = 5.0, height = 2.82, device = "pdf")
ggsave(paste0(out, ".png"), p, width = 5.0, height = 2.82, dpi = 300)
cat("Saved", out, "\n")
