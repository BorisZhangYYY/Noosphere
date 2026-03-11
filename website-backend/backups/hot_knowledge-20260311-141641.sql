--
-- PostgreSQL database dump
--

\restrict XlCglUY93PMtk7fjsG2q6CCzsm8uNNbXlZbCHSceTB428WhVuzVvQrnRgcDISra

-- Dumped from database version 18.3 (Homebrew)
-- Dumped by pg_dump version 18.3 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY public.user_info DROP CONSTRAINT IF EXISTS user_info_username_key;
ALTER TABLE IF EXISTS ONLY public.user_info DROP CONSTRAINT IF EXISTS user_info_pkey;
ALTER TABLE IF EXISTS public.user_info ALTER COLUMN id DROP DEFAULT;
DROP SEQUENCE IF EXISTS public.user_info_id_seq;
DROP TABLE IF EXISTS public.user_info;
SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: user_info; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_info (
    id bigint NOT NULL,
    username text NOT NULL,
    password_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_info_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_info_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_info_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_info_id_seq OWNED BY public.user_info.id;


--
-- Name: user_info id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_info ALTER COLUMN id SET DEFAULT nextval('public.user_info_id_seq'::regclass);


--
-- Data for Name: user_info; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_info (id, username, password_hash, created_at) FROM stdin;
1	demo_user3	scrypt:32768:8:1$v9ePivlOJdv7OLLb$4463f05a564c89206d7432cd8a8ee4a87e2c59b4d1afa11c82b05b1392ae17c220ebf8615a3ac9020521441809cdc6df7ee5c96d7b70e53be9716c75aca4013b	2026-03-11 11:09:49.455024+08
2	boris_demo_001	scrypt:32768:8:1$RxN4KvWkgUxoZh2G$388c2a728b5a8e8d7def7d78dc23e3998adb4f6002401fb484a95a206b02b1014b8b93caea4c5886320c12c3080792f3bb41a9bbd288ed1d890787742f4c105f	2026-03-11 13:38:02.107866+08
\.


--
-- Name: user_info_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.user_info_id_seq', 2, true);


--
-- Name: user_info user_info_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_info
    ADD CONSTRAINT user_info_pkey PRIMARY KEY (id);


--
-- Name: user_info user_info_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_info
    ADD CONSTRAINT user_info_username_key UNIQUE (username);


--
-- PostgreSQL database dump complete
--

\unrestrict XlCglUY93PMtk7fjsG2q6CCzsm8uNNbXlZbCHSceTB428WhVuzVvQrnRgcDISra

