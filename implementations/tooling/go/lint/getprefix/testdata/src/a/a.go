package a

type store struct{}

func (store) Get(key string) string { return key }

func (store) GetName() string { return "" } // want `function name GetName has a Get prefix; name it for the value it returns`

func getValue() int { return 0 } // want `function name getValue has a Get prefix; name it for the value it returns`

func Getter() int { return getValue() }

func get() int { return 0 }

func Target() int { return get() }

func GetÄrger() int { return 0 } // want `function name GetÄrger has a Get prefix; name it for the value it returns`
