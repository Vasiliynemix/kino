-- Схема базы бота. Применяется один раз к пустой базе:
--   psql "$POSTGRES_DB_URL" -f deploy/schema.sql
-- Колонки и таблицы для Пушкинской карты бот при старте досоздаёт сам (pushkin.ensure_schema).


CREATE TABLE public.cinemas (
    building_id bigint NOT NULL,
    name text,
    city text,
    address text,
    fond_kino_id bigint
);

CREATE TABLE public.orders (
    order_id bigint,
    user_id bigint,
    buyer_id bigint,
    performance_id bigint,
    place_id bigint,
    price integer,
    payment_id text,
    payment_link text,
    place_locked_time bigint,
    status integer,
    kino_add_payment_id bigint,
    "row" integer,
    place integer,
    report_sented integer DEFAULT 0,
    uuid_order text NOT NULL,
    payment_msg_id bigint,
    validation text,
    validation_reason text,
    client_ip text,
    validation_started bigint,
    validation_signature text
);

CREATE TABLE public.performance (
    performance_id bigint NOT NULL,
    show_id bigint,
    building_id bigint,
    hallname text,
    minprice integer,
    maxprice integer,
    building_name text,
    hall_id bigint,
    date text,
    "time" text,
    freeplaces integer
);

CREATE TABLE public.pushkin_periods (
    show_id bigint,
    event_id bigint,
    organization_id bigint,
    place_id bigint,
    place_name text,
    city text,
    tz text,
    start_ms bigint,
    end_ms bigint
);

CREATE TABLE public.show (
    show_id bigint NOT NULL,
    name text,
    kinopoisk_id bigint,
    description text,
    poster text,
    kp_rating integer,
    pushkin_card integer DEFAULT 0,
    pu_number bigint,
    id_procult bigint,
    duration text
);

CREATE TABLE public.users (
    user_id bigint NOT NULL,
    city text,
    buyer_id bigint,
    name text,
    surname text,
    patronymic text,
    agreement boolean,
    max_chat_id bigint
);

ALTER TABLE ONLY public.cinemas
    ADD CONSTRAINT cinemas_pkey PRIMARY KEY (building_id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_uuid_order_unique UNIQUE (uuid_order);

ALTER TABLE ONLY public.performance
    ADD CONSTRAINT performance_pkey PRIMARY KEY (performance_id);

ALTER TABLE ONLY public.show
    ADD CONSTRAINT show_pkey PRIMARY KEY (show_id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT unique_user_performance UNIQUE (user_id, performance_id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);

CREATE UNIQUE INDEX order_id_unique ON public.orders USING btree (order_id);

CREATE INDEX pushkin_periods_show_idx ON public.pushkin_periods USING btree (show_id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id);

ALTER TABLE ONLY public.performance
    ADD CONSTRAINT performance_show_id_fkey FOREIGN KEY (show_id) REFERENCES public.show(show_id);


-- Кинотеатры: building_id — ID в билетной системе, fond_kino_id — ID в ЕАИС
INSERT INTO public.cinemas (building_id, name, city, address, fond_kino_id) VALUES (2515, 'Орион', 'Бердск', 'г. Бердск, ул. Островского, 69', 1629) ON CONFLICT (building_id) DO NOTHING;
INSERT INTO public.cinemas (building_id, name, city, address, fond_kino_id) VALUES (3522, 'Планета кино', 'Бийск', 'г. Бийск, ул. Советская, 205/2', 1626) ON CONFLICT (building_id) DO NOTHING;
INSERT INTO public.cinemas (building_id, name, city, address, fond_kino_id) VALUES (5041, 'Планета кино', 'Горно-Алтайск', 'г. Горно-Алтайск, пр. Коммунистический, 11', 1627) ON CONFLICT (building_id) DO NOTHING;
INSERT INTO public.cinemas (building_id, name, city, address, fond_kino_id) VALUES (1511, 'Аврора', 'Новосибирск', 'г. Новосибирск, пр. Карла Маркса, 49', 1632) ON CONFLICT (building_id) DO NOTHING;
INSERT INTO public.cinemas (building_id, name, city, address, fond_kino_id) VALUES (3516, 'Горизонт', 'Новосибирск', 'г. Новосибирск, ул. Бориса Богаткова, 266', 1633) ON CONFLICT (building_id) DO NOTHING;
INSERT INTO public.cinemas (building_id, name, city, address, fond_kino_id) VALUES (1009, 'Россия', 'Искитим', 'г. Искитим, пр. Юбилейный, 15', 1628) ON CONFLICT (building_id) DO NOTHING;
