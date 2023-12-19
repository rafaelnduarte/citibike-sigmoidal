from datetime import timedelta, datetime
from random import sample
import os
import joblib
import pandas as pd
import plotly.express as px
import streamlit as st

import hopsworks

from features import citibike, meteorological_measurements


def print_fancy_header(text, font_size=22, color="#ff5f27"):
    res = f'<span style="color:{color}; font-size: {font_size}px;">{text}</span>'
    st.markdown(res, unsafe_allow_html=True)


st.title('🚲 Previsão de Uso de Bicicletas Citibike 🚲')

st.write(36 * "-")
print_fancy_header('\n📡 Conectando ao Hopsworks Feature Store...')

st.write("Registrando... ")
# (Atenção! Se o aplicativo parar nesta etapa,
# por favor, insira sua chave de API do Hopsworks no prompt de comando.)
project = hopsworks.login()
fs = project.get_feature_store()

st.write("✅ Conectado com sucesso!")

@st.cache_data()
def get_feature_view():
    st.write("Obtendo o Feature View...")
    feature_view = fs.get_feature_view(
        name='citibike_fv',
        version=1
    )
    st.write("✅ Sucesso!")

    return feature_view


feature_view = get_feature_view()


st.write(36 * "-")
print_fancy_header('\n☁️ Recuperando conjunto de treinamento e outros dados do Feature Store...')

@st.cache_data()
def get_data_from_feature_store():
    st.write("🏋️ Recuperando o Conjunto de Treinamento...")
    X_train, X_test, y_train, y_test = feature_view.get_train_test_split(1)

    st.write("📅 Calculando datas para previsão...")
    meteorological_measurements_fg = fs.get_or_create_feature_group(
        name="meteorological_measurements",
        version=1
    )
    last_date = citibike.get_last_date_in_fg(meteorological_measurements_fg)

    st.write("🌆 Obtendo informações das estações...")
    citibike_stations_info_fg = fs.get_or_create_feature_group(
        name="citibike_stations_info",
        version=1
    )
    stations_info_df = citibike_stations_info_fg.read()

    return X_train, last_date, stations_info_df


training_data, last_date, stations_info_df = get_data_from_feature_store()

training_data = training_data.sort_values(["date", "station_id"])
training_data.station_id =  training_data.station_id.astype(str)
st.write("✅ Concluído!")

stations_list = [
    '6170.02', '4729.01', '7976.08', '5190.07', '6896.16', '3847.04',
    '4611.03', '6230.04', '6416.06', '4143.03', '6887.03', '7414.17',
    '7522.02', '5282.02', '4906.07', '4895.09', '6203.02', '5175.08',
    '5156.05', '5788.15', '7567.06', '6584.12', '4517.03', '5117.05',
    '7688.12', '6960.1', '5453.01', '7622.12', '7783.18', '4107.13',
    '6247.06', '6650.07', '6717.06', '4528.01', '5148.03', '4494.04',
    '4404.1', '6551.02', '4175.15', '5308.04', '5545.04', '5001.08',
    '6039.06', '6966.04', '7504.18', '6462.05', '5938.11', '5863.07',
    '5633.04', '6441.01', '5082.08', '5178.06', '7520.07', '3498.09',
    '6762.02', '5470.12', '5267.08', '4437.01', '7009.02', '5374.01'
]

stations_info_dict_1 = stations_info_df.set_index("station_id").to_dict()
stations_info_dict_2 = stations_info_df.set_index("station_name").to_dict()
stations_list_names = list(map(lambda x: stations_info_dict_1["station_name"][x], stations_list))

st.write(36 * "-")
print_fancy_header('\n🗺 Por favor, selecione as estações Citibike para processar...')
with st.form("stations_selection"):
   selected_stations_names = st.multiselect(label='Escolha qualquer número de estações.',
                                            options=stations_list_names,
                                            # deixe o mapa mostrar algum ponto em NYC em vez de uma tela em branco
                                            default=stations_list_names[5])
   # Cada formulário deve ter um botão de envio.
   submitted = st.form_submit_button("Enviar")

selected_stations = list(map(lambda x: stations_info_dict_2["station_id"][x], selected_stations_names))

training_data_batch = training_data.loc[training_data['station_id'].isin(selected_stations)]

stations_info_df = stations_info_df[stations_info_df.station_id.isin(selected_stations)]

st.write(36 * "-")
print_fancy_header('\n🗺 Você selecionou estas estações:')
st.write('💡 Tente clicar no botão "Visualizar em tela cheia" no canto superior direito do widget.')
def get_map(stations_info_df):
    fig = px.scatter_mapbox(stations_info_df,
                            lat="lat",
                            lon="long",
                            zoom=11.5,
                            hover_name="station_name",
                            size=[5] * len(selected_stations)
                            # height=600,
                            # width=700
                            )

    fig.update_layout(mapbox_style="open-street-map")
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    return fig

st.plotly_chart(get_map(stations_info_df))

st.write(36 * "-")
print_fancy_header(text='\n🤖💬 Por quantos dias você quer que eu faça a previsão para cada estação selecionada?',
             font_size=24, color="#00FFFF")
HOW_MANY_DAYS_PREDICT = st.number_input(label='',
                                        min_value=7,
                                        max_value=1000,
                                        step=1,
                                        value=7)
HOW_MANY_DAYS_PREDICT = int(HOW_MANY_DAYS_PREDICT)

st.write(36 * "-")
print_fancy_header('\n🇺🇸 Obtendo o calendário dos EUA para as datas selecionadas...')
us_holidays_fg = fs.get_or_create_feature_group(
    name="us_holidays",
    version=1
)
end_date = datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=HOW_MANY_DAYS_PREDICT)
end_date = datetime.strftime(end_date, "%Y-%m-%d")

holidays_df = us_holidays_fg.filter((us_holidays_fg.timestamp > citibike.convert_date_to_unix(last_date)) & \
                                    (us_holidays_fg.timestamp <= citibike.convert_date_to_unix(end_date))).read()
st.write("✅ Concluído!")

st.write(36 * "-")


def get_model(project, model_name, file_name):
    # carrega nosso Modelo
    list_of_files = [os.path.join(dirpath,filename) for dirpath, _, filenames in os.walk('.') for filename in filenames if filename == file_name]

    if list_of_files:
        model_path = list_of_files[0]
        model = joblib.load(model_path)
    else:
        if not os.path.exists(file_name):
            mr = project.get_model_registry()
            EVALUATION_METRIC="r2_score"
            SORT_METRICS_BY="max"
            # obtém o melhor modelo com base em métricas personalizadas
            model = mr.get_best_model(model_name,
                                      EVALUATION_METRIC,
                                      SORT_METRICS_BY)
            model_dir = model.download()
            model = joblib.load(model_dir + f"/{file_name}")

    return model

print_fancy_header('\n 🤖 Obtendo o modelo...')
regressor = get_model(project=project, model_name="citibike_xgb_model",
                      file_name="citibike_xgb_model.pkl")
st.write("✅ Concluído!")

st.write(36 * "-")
print_fancy_header('\n 🧠 Fazendo previsões...')
temp_date = last_date[:]



res_df = pd.DataFrame()
for i in range(HOW_MANY_DAYS_PREDICT):
    temp_date = citibike.get_next_date(temp_date)

    df_batch = pd.DataFrame({
        "date": [temp_date] * len(selected_stations),
        "station_id": selected_stations,
        "users_count": [-1] * len(selected_stations)
    })

    concat_df = pd.concat([training_data_batch, df_batch], axis=0).reset_index(drop=True)
    concat_df_engineered = citibike.engineer_citibike_features(concat_df)


    agg_cols = concat_df_engineered[concat_df_engineered.date == temp_date] \
                   .drop(columns=["users_count"]).reset_index(drop=True)

    # obtém dados meteorológicos para este dia específico
    weather_row = meteorological_measurements.get_weather_data(city="nyc",
                                   start_date=temp_date,
                                   end_date=temp_date)
    weather_cols = weather_row.loc[weather_row.index.repeat(agg_cols.shape[0])] \
                                  .reset_index(drop=True).drop(columns=["date"])

    X = pd.concat([agg_cols, weather_cols], axis=1).set_index(["date", "station_id"])

    # é feriado neste dia ou não
    holiday_value = holidays_df[holidays_df.date == temp_date]["holiday"].values[0]
    X["holiday"] = [holiday_value] * X.shape[0]


    training_data_batch = pd.concat([training_data_batch, X.reset_index()])
    feature_names = regressor.get_booster().feature_names
    X = X[feature_names]

    preds_temp = regressor.predict(X)

    temp_df = pd.DataFrame()
    temp_df.index = X.index

    # salva as previsões em temp_df
    temp_df = temp_df.assign(prediction=preds_temp)

    # adiciona novas observações a res_df
    res_df = pd.concat([res_df, temp_df])

st.write("✅ Concluído!")
st.write(res_df.tail(5))

st.write(36 * "-")
print_fancy_header('\n📈 Plotando nossos resultados...')
st.write('💡 Tente clicar no botão "Visualizar em tela cheia" no canto superior direito do widget.')
df_for_vizual = res_df.copy().reset_index()
df_for_vizual.station_id = df_for_vizual.station_id.apply(
                               lambda x: stations_info_dict_1["station_name"][x])
df_for_vizual = df_for_vizual.rename(columns={"station_id": "station_name"})

df_for_vizual = df_for_vizual.pivot(index='date',
                                    columns='station_name',
                                    values='prediction')


res_fig = px.area(df_for_vizual,
                  facet_col="station_name", facet_col_wrap=2,
                  labels={
                     "value": ""
                 })

st.plotly_chart(res_fig)

st.write(36 * "-")
st.subheader('\n🎉 📈 🤝 Aplicativo Concluído com Sucesso 🤝 📈 🎉')
st.button("Reiniciar")
