FROM apache/airflow:2.9.3-python3.11

USER airflow

# Dependances Python des DAGs. Airflow est epingle pour ne pas etre mis a jour, et scipy est
# epingle sur une version compatible avec le numpy 1.26 fourni par l'image.
RUN pip install --no-cache-dir "apache-airflow==2.9.3" \
      azure-storage-blob==12.22.0 \
      azure-identity==1.17.1 \
      pyarrow==17.0.0 \
      scipy==1.13.1 \
      statsmodels==0.14.2 \
      vaderSentiment==3.3.2 \
      defusedxml==0.7.1

# dbt dans un virtualenv separe pour eviter les conflits de dependances avec Airflow.
# dbt-core est epingle : dbt-postgres 1.8 n'impose pas de borne haute et pip installerait dbt-core 2.x.
RUN python -m venv /home/airflow/dbt-venv \
 && /home/airflow/dbt-venv/bin/pip install --no-cache-dir "dbt-core==1.8.8" "dbt-postgres==1.8.2"
