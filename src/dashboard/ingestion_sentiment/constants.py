"""Constants for sentiment ingestion jobs."""

DOMAIN_SENTIMENT = "sentiment"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

JOB_TYPE_SENTIMENT_REDDIT_REFRESH = "sentiment_reddit_refresh"
JOB_TYPE_SENTIMENT_X_REFRESH = "sentiment_x_refresh"
JOB_TYPE_NEWS_RSS_REFRESH = "news_rss_refresh"
JOB_TYPE_NEWS_PROVIDER_REFRESH = "news_provider_refresh"
JOB_TYPE_SENTIMENT_DAILY_AGGREGATE = "sentiment_daily_aggregate"
JOB_TYPE_FACTOR_SNAPSHOT_REFRESH = "factor_snapshot_refresh"
JOB_TYPE_QUANT_RATING_REFRESH = "quant_rating_refresh"

DATASET_REDDIT = "reddit"
DATASET_X = "x"
DATASET_NEWS = "news"
DATASET_SENTIMENT_DAILY = "sentiment_daily"
DATASET_FACTOR_SNAPSHOT = "factor_snapshot"
DATASET_QUANT_RATING = "quant_rating"

PRIORITY_RETAIL_REFRESH = 40
PRIORITY_NEWS_REFRESH = 35
PRIORITY_DAILY_AGGREGATE = 30
PRIORITY_FACTOR_REFRESH = 20
PRIORITY_QUANT_REFRESH = 10

