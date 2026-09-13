import request from './request'

export const login = (username, password) =>
  request.post('/auth/login', { username, password })

export const getMe = () => request.get('/auth/me')

export const getKey = () => request.get('/key')

export const updateKey = (key) => request.put('/key', { key })

export const getLogs = (params) => request.get('/logs', { params })

export const getBans = (params) => request.get('/bans', { params })

export const addBan = (data) => request.post('/bans', data)

export const updateBan = (id, data) => request.put(`/bans/${id}`, data)

export const deleteBan = (id) => request.delete(`/bans/${id}`)

export const getStats = () => request.get('/stats')
